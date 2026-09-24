"""Core Freeze V4: the scientific-core re-audit's contract, with a compatibility proof that can fail.

    python -m tools.certification.core_freeze_v4 --build --candidate <commit>
    python -m tools.certification.core_freeze_v4 --verify

WHY A FOURTH FREEZE
-------------------
The 2026-09-16 scientific core re-audit changed shapes in fifty-five batches, all of them additively:
new enum members, new trailing dataclass fields with defaults, new keyword arguments with defaults,
new private helpers. Nineteen FAST-tier tests have been failing by design the whole time, because the
V1 frozen digest moved (``c80e6418`` to ``f18aa806``), four pinned snapshots describe the pre-round
surface, and the V2 and V3 manifests state a contract the hardened readers now refuse. That is the
state finding 89 names: **the branch descends from no Core Freeze, and recertification is blocked.**

V4 is where the round's own result becomes certifiable. The one thing it must not do is regenerate a
snapshot and call the result compatible, so:

* **the comparison is against the STORED V1 bytes.** ``stored_v1_frozen_snapshot`` reads
  ``tests/api/frozen_api_snapshot.json`` AS COMMITTED at the Core Freeze V1 baseline commit and
  checks those bytes against the digest V1's own manifest pinned. Finding 95 is that
  ``v1_entries_byte_identical_in_v2`` compared the live surface with the live surface, which is true
  by construction;
* **additive is enumerated, not asserted.** :func:`additive_only_problems` names every non-additive
  difference it finds: a removed or renamed symbol, a removed parameter, a changed default, a changed
  parameter kind, a new parameter without a default, an enum member removed, revalued, inserted or
  REORDERED, a dataclass field removed, reordered or inserted before the last, a new field without a
  default, a changed exception chain, a changed union membership. Byte identity would have been the
  wrong claim: under an additive-only rule it can only be satisfied by changing nothing;
* **the deep surface is recorded.** ``tools/certification/api_surface_v4.py`` carries method
  signatures and enum member POSITIONS -- finding 94's two deleted methods moved no digest -- pinned
  in ``certification/core_v4_api_surface.json``. ``engcore.api_snapshot`` is untouched, so V1, V2 and
  V3 keep computing what they always computed;
* **the supersession names its rule.** V3's identity references are ``route_diagnostics/1`` records
  carrying no thresholds and a nan chi-square minimum, which this round refuses. Finding 96 is that
  the V3 check counted ANY exception as the refusal and passed when the rule was deleted and an
  ImportError raised instead. :func:`is_the_core_refusal` requires the exception to come from
  ``engcore`` and to name the rule;
* **every figure is re-derived.** Finding 91: a fabricated record with green flags and a copied
  population sha passed every V2/V3 assurance check. :func:`v4_mutation_problems` recomputes the
  population's two digests from the tree, each shard's log digest from the transcript's own bytes,
  each shard's verdicts by parsing that transcript, and the shards' union and disjointness -- and a
  record that disagrees with any of it is refused.

V1, V2 and V3 manifests, assurance records and tags are untouched and are recorded here by digest: a
manifest is a record of its own commit and is never rewritten.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from typing import Any, Mapping, Sequence

from tools.certification import api_surface_v4 as surface
from tools.certification import core_freeze_v2 as v2
from tools.certification import core_freeze_v3 as v3

MANIFEST_SCHEMA = "engcore.core_freeze/4"
ASSURANCE_SCHEMA = "engcore.core_freeze_assurance/4"
MANIFEST_PATH = "certification/core_freeze_v4.json"
ASSURANCE_PATH = "certification/core_freeze_v4_assurance.json"
REPORT_PATH = "certification/CORE_FREEZE_V4.md"
SURFACE_PATH = "certification/core_v4_api_surface.json"
V1_MANIFEST_PATH = v2.V1_MANIFEST_PATH
V2_MANIFEST_PATH = v2.MANIFEST_PATH
V3_MANIFEST_PATH = v3.MANIFEST_PATH
TAG = "v4.0-core-freeze"

#: The frozen snapshot file V1 pinned, read from the V1 baseline commit.
V1_FROZEN_SNAPSHOT_FILE = "tests/api/frozen_api_snapshot.json"

#: The refusal V4's supersession claim rests on: raised BY THE CORE, and naming the rule. Finding 96
#: is what happens without the second half -- an ImportError read as the rule firing.
REQUIRED_V3_REFUSAL = ("engcore.hybrid_uq.vocabulary.HybridUQError",
                       "contradict their own measurements")

#: Certificate areas V4 requires: V3's, plus the harness area whose closure this round derived.
REQUIRED_CERTIFICATE_AREAS = v3.REQUIRED_CERTIFICATE_AREAS + ("harness", "certification_control")

SUPERSEDES_V3_BECAUSE = (
    "R-01/R-20: a route's goodness of fit is re-derived from the numbers it carries, and a "
    "`route_diagnostics/1` record that names no thresholds and no chi-square minimum is refused -- "
    "which is what V3's own identity references are, so V3's serialization inventory can no longer "
    "be reproduced by a correct tree",
    "R-43: a quantified uncertainty record nobody attributed can no longer be aggregated into a "
    "channel total, so an SRIA budget built from V3's unattributed records is refused",
    "R-58/R-61: a recorded transfer states where its value came from and is checked against the "
    "result it names, so a crossing carrying a bare point value no longer round-trips",
    "R-67/R-68: the certificate's harness area is derived from what its suites import, so a V3 "
    "certificate's scope table is not a V4 scope table",
)

CAPABILITY_CLAIM = (
    "Core Freeze V4 is the 2026-09-16 scientific core re-audit's contract: 75 problems measured, "
    "and the shapes the fixes needed added WITHOUT removing, renaming, reordering or re-defaulting "
    "anything a consumer holds. The claim is not that the API is unchanged -- it is that every "
    "difference from the Core Freeze V1 surface, as V1 itself committed it, is one of the four "
    "additive kinds the owner allowed, proved difference by difference by additive_only_problems."
)

NON_CLAIMS = (
    "V4 does not claim any domain solver quantifies its uncertainty: every one still reports UNKNOWN "
    "with a stated reason (R-43's remaining half).",
    "V4 does not claim the deep surface covers behaviour. Methods are recorded by name and "
    "signature; what they do is what the 575-mutation population and the suites are for.",
    "V4 does not claim a fresh execution. The assurance record states which commit it measured and "
    "every figure in it is re-derived from the tree and the transcripts; binding that to an "
    "execution is the recertify workflow's job.",
    "V4 does not re-freeze the mesh and parameter identities (R-62, R-74): I-23 is deferred and is "
    "listed as an open decision in the audit document.",
)

REQUIRED_SUITES = ()  # see REQUIRED_V4_SUITES, declared beside the commands that produce them


# =====================================================================
# the stored V1 surface, and what additive means
# =====================================================================
def descends_from(root: pathlib.Path, ancestor: str, commit: str) -> bool:
    """Whether ``commit`` descends from ``ancestor`` in this repository.

    A named function rather than a line inside :func:`verify`, so the rule R-65's first sentence is
    about -- *the branch descends from no Core Freeze* -- can be tested at its own boundary: an empty
    or unknown ancestor is False, never "nothing to check".
    """
    if not ancestor or not commit:
        return False
    return subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, commit],
                          cwd=root, capture_output=True).returncode == 0


def _historical_assurance_problems(root: pathlib.Path, assurance: Mapping[str, Any]) -> list[str]:
    """Why the stored V4 assurance is not the immutable record created from its measured tree.

    The V4 assurance file is historical evidence, not a live pin on every future descendant's
    mutation population.  Re-deriving its 589-mutant record against a later tree that deliberately
    grew the population to 680 turns ordinary certified evolution into a false freeze failure.

    What must remain binding on descendants is the historical chain itself: the assurance file was
    added exactly once, its bytes have never been rewritten, and the commit that added it is the
    one-parent child of the commit the record says it measured.
    """
    problems: list[str] = []
    history = subprocess.run(
        ["git", "log", "--format=%H", "--", ASSURANCE_PATH],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if history.returncode != 0:
        return [f"cannot read {ASSURANCE_PATH} history: {history.stderr.strip()[:200]}"]
    commits = tuple(line.strip() for line in history.stdout.splitlines() if line.strip())
    if len(commits) != 1:
        problems.append(
            f"{ASSURANCE_PATH} must be an immutable one-commit historical record; "
            f"git history contains {len(commits)} touching commit(s)"
        )
        return problems

    record_commit = commits[0]
    stored = subprocess.run(
        ["git", "show", f"{record_commit}:{ASSURANCE_PATH}"],
        cwd=root,
        capture_output=True,
    )
    if stored.returncode != 0:
        problems.append(
            f"cannot read {ASSURANCE_PATH} from its history commit {record_commit[:12]}"
        )
    elif stored.stdout != (root / ASSURANCE_PATH).read_bytes():
        problems.append(
            f"{ASSURANCE_PATH} differs from the bytes first committed at {record_commit[:12]}"
        )

    parent = subprocess.run(
        ["git", "show", "-s", "--format=%P", record_commit],
        cwd=root,
        capture_output=True,
        text=True,
    )
    parents = tuple(parent.stdout.strip().split()) if parent.returncode == 0 else ()
    measured = str(assurance.get("measured_commit", "")).strip()
    if parents != (measured,):
        problems.append(
            f"the assurance commit {record_commit[:12]} must be the one-parent child of "
            f"its measured commit {measured[:12] or '(missing)'}; parents are "
            f"{[item[:12] for item in parents]}"
        )
    return problems


def stored_v1_frozen_snapshot(root: pathlib.Path) -> dict[str, Any]:
    """The frozen snapshot AS COMMITTED at the Core Freeze V1 baseline, with its two digests.

    Read out of git rather than off disk, and checked against the digest V1's own manifest pinned:
    the point of finding 95 is that a comparison against the live tree cannot fail.
    """
    manifest = json.loads((root / V1_MANIFEST_PATH).read_bytes())
    baseline = manifest["freeze"]["baseline_commit"]
    done = subprocess.run(["git", "show", f"{baseline}:{V1_FROZEN_SNAPSHOT_FILE}"],
                          cwd=root, capture_output=True)
    if done.returncode != 0:
        raise RuntimeError(
            f"{V1_FROZEN_SNAPSHOT_FILE} is not in commit {baseline[:12]}, so the V1 surface cannot be "
            f"read as V1 committed it: {done.stderr.decode('utf-8', 'replace')[:200]}")
    blob = done.stdout
    snapshot = json.loads(blob.decode("utf-8"))
    from engcore import api_snapshot

    return {
        "commit": baseline,
        "file": V1_FROZEN_SNAPSHOT_FILE,
        "file_sha256": v2.sha256_bytes(blob),
        "digest": api_snapshot.digest(snapshot),
        "snapshot": snapshot,
    }



def stored_frozen_snapshot(root: pathlib.Path, *, commit: str, relative: str) -> dict[str, Any]:
    """One committed snapshot file, read out of git, with its file digest and its own digest.

    The general form of :func:`stored_v1_frozen_snapshot`: the V2 surface is checked the same way,
    against the bytes Core Freeze V2 pinned, because a comparison against the live tree is the defect
    finding 95 names whichever surface it is about.
    """
    done = subprocess.run(["git", "show", f"{commit}:{relative}"], cwd=root, capture_output=True)
    if done.returncode != 0:
        raise RuntimeError(
            f"{relative} is not in commit {commit[:12]}: {done.stderr.decode('utf-8', 'replace')[:200]}")
    from engcore import api_snapshot

    snapshot = json.loads(done.stdout.decode("utf-8"))
    return {"commit": commit, "file": relative, "file_sha256": v2.sha256_bytes(done.stdout),
            "digest": api_snapshot.digest(snapshot), "snapshot": snapshot}


def stored_v2_frozen_snapshot(root: pathlib.Path) -> dict[str, Any]:
    """The V2 frozen snapshot as Core Freeze V2 committed it, checked against V2's own pinned digest."""
    manifest = json.loads((root / V2_MANIFEST_PATH).read_bytes())
    relative = "tests/api/v2_frozen_api_snapshot.json"
    stored = stored_frozen_snapshot(root, commit=manifest["freeze"]["candidate_commit"], relative=relative)
    pinned = manifest["pinned_v2_snapshot_files"][relative]
    if stored["file_sha256"] != pinned:
        raise RuntimeError(
            f"{relative} at the V2 freeze commit hashes {stored['file_sha256'][:16]} and the V2 manifest "
            f"pinned {pinned[:16]}: the stored surface is not the one V2 recorded")
    return stored


def _by_key(snapshot: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {(e["module"], e["name"]): e for e in snapshot.get("symbols", ())}


def _parameter_problems(label: str, stored, live) -> list[str]:
    """Why a signature change is not additive. A new argument is additive only WITH a default."""
    if stored is None and live is None:
        return []
    if stored is None or live is None:
        return [f"{label}: a signature appeared or disappeared"]
    old = {p["name"]: p for p in stored.get("parameters", ())}
    new = {p["name"]: p for p in live.get("parameters", ())}
    problems = []
    for name, parameter in old.items():
        if name not in new:
            problems.append(f"{label}: parameter {name!r} was removed")
            continue
        after = new[name]
        if parameter.get("kind") != after.get("kind"):
            problems.append(
                f"{label}: parameter {name!r} changed kind {parameter.get('kind')} -> {after.get('kind')}")
        if parameter.get("has_default") != after.get("has_default"):
            problems.append(f"{label}: parameter {name!r} gained or lost its default")
        elif v2.canonical(parameter.get("default")) != v2.canonical(after.get("default")):
            problems.append(f"{label}: parameter {name!r} changed default")
    for name, parameter in new.items():
        if name not in old and not parameter.get("has_default"):
            problems.append(f"{label}: new parameter {name!r} has no default, so every caller breaks")
    old_order = [name for name in old if name in new]
    new_order = [name for name in new if name in old]
    if old_order != new_order:
        problems.append(f"{label}: the parameters that existed before were reordered")
    return problems


def _field_problems(label: str, stored, live) -> list[str]:
    if stored is None and live is None:
        return []
    if stored is None or live is None:
        return [f"{label}: the dataclass fields appeared or disappeared"]
    old = {f["name"]: f for f in stored}
    new = {f["name"]: f for f in live}
    problems = []
    for name in old:
        if name not in new:
            problems.append(f"{label}: field {name!r} was removed")
    kept_before = [f["name"] for f in stored if f["name"] in new]
    kept_after = [f["name"] for f in live if f["name"] in old]
    if kept_before != kept_after:
        problems.append(f"{label}: the fields that existed before were reordered")
    added = [f["name"] for f in live if f["name"] not in old]
    names_after = [f["name"] for f in live]
    for name in added:
        if not new[name].get("has_default"):
            problems.append(f"{label}: new field {name!r} has no default")
        if names_after.index(name) < max(
                (names_after.index(kept) for kept in kept_after), default=-1):
            problems.append(
                f"{label}: new field {name!r} is not after the fields that existed before, so every "
                f"positional construction moves")
        stored_default = old.get(name)
        if stored_default is not None and v2.canonical(stored_default) != v2.canonical(new[name]):
            problems.append(f"{label}: field {name!r} changed its default")
    for name in old:
        if name in new and v2.canonical(old[name]) != v2.canonical(new[name]):
            problems.append(f"{label}: field {name!r} changed its default or its init flag")
    return problems


def _enum_problems(label: str, stored, live) -> list[str]:
    """Why an enum change is not additive.

    Removed, renamed or revalued members are breaks, and so is a REORDER: the members that existed
    before must still be in their old relative order. An INSERTION is not a reorder -- every member
    a consumer named is still there, with its value, and still before the members it was before --
    but it does move absolute positions, which is what finding 95 measured and nothing detected. So
    it is not a problem here and it is not silent either: :func:`enum_insertions` lists it and the
    V4 manifest records it, and the audit document carries it as an open decision for the owner,
    whose compatibility rule forbids reordering and does not say which of the two an insertion is.
    """
    if not stored and not live:
        return []
    if stored is None or live is None:
        return [f"{label}: the enum members appeared or disappeared"]
    problems = []
    old = {m["name"]: m["value"] for m in stored}
    new = {m["name"]: m["value"] for m in live}
    for name, value in old.items():
        if name not in new:
            problems.append(f"{label}: member {name!r} was removed")
        elif new[name] != value:
            problems.append(f"{label}: member {name!r} changed value {value!r} -> {new[name]!r}")
    before = [m["name"] for m in stored if m["name"] in new]
    after = [m["name"] for m in live if m["name"] in old]
    if before != after:
        problems.append(f"{label}: the members that existed before were reordered")
    return problems


def enum_insertions(stored: Mapping[str, Any], live: Mapping[str, Any]) -> dict[str, Any]:
    """Every enum where a new member went in BEFORE a member that already existed.

    Additive by the rule above, and RECORDED because finding 95's complaint is that 13 RouteReason
    members changed position with nothing noticing. Each entry names the inserted members and the
    positions they took, so the next insertion is a visible change to this file rather than a
    discovery.
    """
    old, new = _by_key(stored), _by_key(live)
    found: dict[str, Any] = {}
    for key in sorted(set(old) & set(new)):
        stored_members = old[key].get("enum_members") or []
        live_members = new[key].get("enum_members") or []
        if not stored_members or not live_members:
            continue
        existing = {m["name"] for m in stored_members}
        names = [m["name"] for m in live_members]
        added = [name for name in names if name not in existing]
        if not added:
            continue
        last_existing = max((index for index, name in enumerate(names) if name in existing), default=-1)
        inserted = [name for name in added if names.index(name) < last_existing]
        if inserted:
            found[f"{key[0]}.{key[1]}"] = {
                "members_before": len(stored_members),
                "members_now": len(live_members),
                "inserted_before_an_existing_member": inserted,
                "positions": [names.index(name) for name in inserted],
                "existing_members_keep_their_relative_order": True,
            }
    return found



def _constant_problems(label: str, stored, live) -> list[str]:
    """Why a frozen constant's recorded value is not an additive change.

    A GROWN immutable container of the same type is additive, and it is the one case here that was
    decided in advance rather than now: batch 13 preregistered it in words --
    "EVIDENCE_IDENTITY_FIELDS grows from 7 entries to 8, which the V1 snapshot records as a SIZE:
    that is the same additive category as a new enum member, and the snapshot is regenerated in the
    V4 round". A tuple of field names that gains a trailing name is the constant form of appending an
    enum member: every name a consumer read is still there, in its place.

    A SHRUNK container, a changed type, or any change to a scalar constant is a break. And the limit
    is stated rather than hidden: the snapshot records a container's TYPE and SIZE, not its members,
    so a tuple whose eighth entry replaced its seventh would be invisible here -- which is why the
    suites assert the members by name (`tests/test_evidence_identity.py` and the pairing refusals)
    and why this rule accepts only growth.
    """
    if v2.canonical(stored) == v2.canonical(live):
        return []
    if isinstance(stored, Mapping) and isinstance(live, Mapping) \
            and stored.get("kind") == live.get("kind") == "immutable_container" \
            and stored.get("type") == live.get("type") \
            and isinstance(stored.get("size"), int) and isinstance(live.get("size"), int) \
            and live["size"] > stored["size"]:
        return []
    return [f"{label}: the frozen constant's value changed {stored!r} -> {live!r}"]


def additive_only_problems(stored: Mapping[str, Any], live: Mapping[str, Any]) -> list[str]:
    """Every difference between two frozen snapshots that is NOT one of the additive kinds.

    The owner's rule for this round, enumerated: a new symbol, an appended enum member, an appended
    dataclass field with a default and a new keyword argument with a default are additive. Everything
    else -- a removal, a rename, a reorder, a changed default, a changed kind, a new required
    argument -- is a break, and is named here with the symbol it is in.
    """
    old, new = _by_key(stored), _by_key(live)
    problems: list[str] = []
    for key in sorted(set(old) - set(new)):
        problems.append(f"{key[0]}.{key[1]}: the frozen symbol is gone (removed or renamed)")
    for key in sorted(set(old) & set(new)):
        label = f"{key[0]}.{key[1]}"
        before, after = old[key], new[key]
        if before.get("kind") != after.get("kind"):
            problems.append(f"{label}: kind changed {before.get('kind')} -> {after.get('kind')}")
        if before.get("classification") != after.get("classification"):
            problems.append(
                f"{label}: classification changed {before.get('classification')} -> "
                f"{after.get('classification')}")
        if before.get("exception_mro") != after.get("exception_mro"):
            problems.append(f"{label}: the exception chain changed, so `except` clauses move")
        if before.get("union_members") != after.get("union_members"):
            problems.append(f"{label}: the union's members changed")
        problems += _parameter_problems(label, before.get("signature"), after.get("signature"))
        problems += _field_problems(label, before.get("dataclass_fields"), after.get("dataclass_fields"))
        problems += _enum_problems(label, before.get("enum_members"), after.get("enum_members"))
        if before.get("kind") == "constant":
            problems += _constant_problems(label, before.get("value"), after.get("value"))
    return problems


# =====================================================================
# the supersession, and which rule refused
# =====================================================================
def is_the_core_refusal(required_exception: str, required_phrase: str, *, exception: str, message: str) -> bool:
    """Whether what was raised IS the rule V4's supersession rests on.

    Finding 96: the V3 check caught ``Exception`` and read any of them as the refusal, so it passed
    with the rule deleted and an ImportError raised in its place. Two things are required: the
    exception is the core's own class, and the message names the rule.
    """
    return exception == required_exception and required_phrase in message


def v3_fixtures_refused() -> dict[str, Any]:
    """Whether this tree refuses V3's identity references, and WHICH rule did it."""
    try:
        v3.fixture_records()
    except BaseException as raised:  # noqa: BLE001 - the type is the evidence and is recorded
        name = f"{type(raised).__module__}.{type(raised).__qualname__}"
        message = str(raised)
        return {
            "refused": is_the_core_refusal(*REQUIRED_V3_REFUSAL, exception=name, message=message),
            "exception": name,
            "message": message[:600],
            "required_exception": REQUIRED_V3_REFUSAL[0],
            "required_phrase": REQUIRED_V3_REFUSAL[1],
        }
    return {"refused": False, "exception": "", "message": "V3's fixture records were accepted",
            "required_exception": REQUIRED_V3_REFUSAL[0], "required_phrase": REQUIRED_V3_REFUSAL[1]}


# =====================================================================
# the mutation round, re-derived
# =====================================================================
def v4_mutation_assurance(root: pathlib.Path, *, logs: Mapping[int, bytes], source_commit: str,
                          shard_count: int | None = None) -> dict[str, Any]:
    """The ``v4_guard_mutations`` block, computed from the tree and the transcripts themselves."""
    from tools.certification import mutation_population as mp

    count = mp.SHARD_COUNT if shard_count is None else shard_count
    population = mp.v4_population(root)
    shards = {}
    for index in sorted(logs):
        selected = population.shard(index, count)
        shards[str(index)] = {
            "selected_count": len(selected),
            "selected_ids_sha256": mp.sha256_lines(selected),
            "execution_log_sha256": v2.sha256_bytes(logs[index]),
            "execution_log_bytes": len(logs[index]),
        }
    return {
        "population_path": mp.V4_POPULATION_PATH,
        "runner": "tools/certification/mutation_v4_runner.py",
        "source_commit": source_commit,
        "population": population.count,
        "expected_population": mp.EXPECTED_V4_POPULATION,
        "population_sha256": population.sha256,
        "definitions_sha256": population.definitions_sha256,
        "shard_count": count,
        "sharding_rule": "shard i runs the ids at positions p where p % shard_count == i",
        "kill_rule": ("a mutation is KILLED only when the ONE test its entry names carries a <failure> "
                      "in that run's own JUnit report"),
        "shards": shards,
    }


def v4_mutation_problems(root: pathlib.Path, record: Mapping[str, Any], *,
                         logs: Mapping[int, bytes] | None = None) -> list[str]:
    """Why a V4 mutation record is not evidence. Every figure is recomputed, none is read."""
    from tools.certification import mutation_population as mp

    population = mp.v4_population(root)
    problems = list(population.problems(mp.EXPECTED_V4_POPULATION))
    count = record.get("shard_count")
    if count != mp.SHARD_COUNT:
        problems.append(f"the record shards into {count}, and the population's rule is {mp.SHARD_COUNT}")
        count = mp.SHARD_COUNT
    if record.get("population_sha256") != population.sha256:
        problems.append(
            f"the record names population {str(record.get('population_sha256'))[:16]} and the tree's is "
            f"{population.sha256[:16]}")
    if record.get("definitions_sha256") != population.definitions_sha256:
        problems.append("the record's mutation definitions are not the ones in the tree")
    if record.get("population") != population.count:
        problems.append(f"the record counts {record.get('population')} mutations, the tree has {population.count}")
    shards = record.get("shards") or {}
    union: list[str] = []
    for index in range(count):
        entry = shards.get(str(index))
        if entry is None:
            problems.append(f"shard {index}: no record")
            continue
        selected = population.shard(index, count)
        union.extend(selected)
        if entry.get("selected_count") != len(selected):
            problems.append(f"shard {index}: records {entry.get('selected_count')} ids, the rule selects {len(selected)}")
        if entry.get("selected_ids_sha256") != mp.sha256_lines(selected):
            problems.append(f"shard {index}: the recorded ids are not the ones its shard rule selects")
        if logs is None:
            continue
        log = logs.get(index)
        if log is None:
            problems.append(f"shard {index}: no transcript to re-derive its verdicts from")
            continue
        if v2.sha256_bytes(log) != entry.get("execution_log_sha256"):
            problems.append(f"shard {index}: the transcript's digest is not the one recorded")
        problems += [f"shard {index}: {problem}" for problem in
                     mp.v4_log_problems(log.decode("utf-8", "replace"), population, selected)]
    duplicates = sorted({mid for mid in union if union.count(mid) > 1})
    if duplicates:
        problems.append(f"mutations executed by more than one shard: {duplicates}")
    missing = [mid for mid in population.ids if mid not in set(union)]
    if missing:
        problems.append(f"mutations no shard executed: {missing[:10]}{'...' if len(missing) > 10 else ''}")
    return problems



# =====================================================================
# the assurance record, built from evidence and never from a claim
# =====================================================================
#: Where the V4 round's transcripts are committed. A shard's evidence is its transcript, and a
#: transcript nobody can read is a figure somebody typed.
TRANSCRIPT_DIR = "benchmarks/core_v4_false_confidence/v4_round"

#: The suites a V4 assurance record must carry green. The four freeze/API suites are the ones the
#: certificate child runs for the deferred self-checks, so a record that omits one is a record whose
#: green FAST tier says nothing about the contract.
REQUIRED_V4_SUITES = ("FAST", "population_v4", "freeze_manifest_v4", "api_snapshot_v1",
                      "api_snapshot_v2", "certificate")

V4_SUITE_COMMANDS: dict[str, tuple[str, ...]] = {
    "FAST": ("-m", "not expensive", "-q", "-n", "4", "--dist", "loadfile"),
    "population_v4": ("-q", "tests/test_mutation_population_v4.py", "tests/test_mutation_harness.py"),
    "freeze_manifest_v4": ("-q", "tests/test_core_freeze_v4_manifest.py",
                           "tests/test_core_freeze_v3_manifest.py", "tests/test_core_freeze_manifest.py"),
    "api_snapshot_v1": ("-q", "tests/test_core_api_snapshot.py", "tests/test_core_api_contracts.py"),
    "api_snapshot_v2": ("-q", "tests/test_core_v2_api_snapshot.py", "tests/test_core_v2_compatibility.py"),
    "certificate": ("-q", "tests/test_core_certificate.py", "tests/test_certification_control_plane.py",
                    "tests/test_recertification_scope.py"),
}


def _run_suite(root: pathlib.Path, arguments: Sequence[str]) -> dict[str, Any]:
    done = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", *arguments],
                          cwd=root, capture_output=True, text=True)
    lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return {"exit_code": done.returncode, "green": done.returncode == 0,
            "summary_line": lines[-1] if lines else "(no output)",
            "arguments": list(arguments)}


def build_assurance(root: pathlib.Path, *, run_suites: bool = True) -> dict[str, Any]:
    """The V4 assurance record: the round's transcripts, the suites, and figures derived from both.

    Nothing here is copied from another record. The population's digests come from the tree, each
    shard's log digest from the transcript's bytes, each shard's verdicts from parsing those lines,
    and the measured commit from ``git rev-parse``. That is finding 91 in one sentence: a figure a
    record asserts about itself is not evidence.
    """
    transcripts = {}
    logs: dict[int, bytes] = {}
    for path in sorted((root / TRANSCRIPT_DIR).glob("shard*.log")):
        index = int(path.stem.replace("shard", ""))
        transcripts[str(index)] = path.relative_to(root).as_posix()
        logs[index] = path.read_bytes()
    if not logs:
        raise RuntimeError(f"no shard transcript under {TRANSCRIPT_DIR}: there is no round to assure")
    manifest_file = root / MANIFEST_PATH
    manifest = json.loads(manifest_file.read_bytes())
    measured = v2.git(root, "rev-parse", "HEAD")
    mutations = v4_mutation_assurance(root, logs=logs, source_commit=measured)
    problems = v4_mutation_problems(root, mutations, logs=logs)
    if problems:
        raise RuntimeError("the round's own evidence does not support a record: " + "; ".join(problems[:6]))
    suites = {}
    if run_suites:
        for name in REQUIRED_V4_SUITES:
            suites[name] = _run_suite(root, V4_SUITE_COMMANDS[name])
            suites[name]["deselected_certificate_child_self_checks"] = []
    return {
        "schema": ASSURANCE_SCHEMA,
        "audit": "docs/audits/CORE_REAUDIT_2026-09-16.md",
        "candidate_commit": manifest["freeze"]["candidate_commit"],
        "measured_commit": measured,
        "manifest_sha256": v2.sha256_bytes(manifest_file.read_bytes()),
        "transcripts": transcripts,
        "evidence": {path: v2.sha256_bytes((root / path).read_bytes()) for path in transcripts.values()},
        "mutations": {"v4": mutations},
        "suites": suites,
        "claim": (
            "Fresh execution of the 589-mutation V4 guard population in four shards at the measured "
            "commit, each mutation in an isolated copy of the tree and each verdict read from the "
            "JUnit report of the ONE test its entry names. Every figure in this record is re-derived "
            "by tools.certification.core_freeze_v4.v4_mutation_problems from the tree and from these "
            "transcripts' own bytes; none is read from the record."
        ),
    }


# =====================================================================
# build and verify
# =====================================================================
def api_facts(root: pathlib.Path) -> dict[str, Any]:
    """What V4 claims about the surface, every figure computed here and none read from a record."""
    from engcore import api_snapshot

    stored_v1 = stored_v1_frozen_snapshot(root)
    live_v1 = api_snapshot.frozen_only()
    stored_v2 = stored_v2_frozen_snapshot(root)
    live_v2 = api_snapshot.frozen_only(api_snapshot.build(modules=api_snapshot.V2_CANONICAL_MODULES))
    return {
        "v1_stored": {"commit": stored_v1["commit"], "file": stored_v1["file"],
                      "file_sha256": stored_v1["file_sha256"], "frozen_digest": stored_v1["digest"]},
        "v2_stored": {"commit": stored_v2["commit"], "file": stored_v2["file"],
                      "file_sha256": stored_v2["file_sha256"], "frozen_digest": stored_v2["digest"]},
        "v4_live": {"frozen_digest": api_snapshot.frozen_digest(),
                    "frozen_count": live_v1["symbol_count"],
                    "total_count": api_snapshot.build()["symbol_count"],
                    "v2_frozen_digest": api_snapshot.frozen_digest(
                        api_snapshot.build(modules=api_snapshot.V2_CANONICAL_MODULES)),
                    "v2_frozen_count": live_v2["symbol_count"]},
        "additive_only_problems": additive_only_problems(stored_v1["snapshot"], live_v1),
        "v2_additive_only_problems": additive_only_problems(stored_v2["snapshot"], live_v2),
        "enum_insertions": enum_insertions(stored_v1["snapshot"], live_v1),
        "v2_enum_insertions": enum_insertions(stored_v2["snapshot"], live_v2),
        "deep_surface": {"path": SURFACE_PATH, "schema": surface.SCHEMA,
                         "digest": surface.digest(), "method_count": surface.build()["method_count"]},
    }


def build_manifest(root: pathlib.Path, candidate: str) -> dict[str, Any]:
    v3_manifest = json.loads((root / V3_MANIFEST_PATH).read_bytes())
    return {
        "schema": MANIFEST_SCHEMA,
        "freeze": {
            "name": "Core Freeze V4", "tag": TAG, "candidate_commit": candidate,
            "descends_from_v3_commit": v3_manifest["freeze"]["candidate_commit"],
            "additive_over": "Core Freeze V1 (v1.0-core-freeze), PROVED difference by difference",
            "supersedes": "Core Freeze V3 (v3.0-core-freeze) contract, for descendants; V1-V3 history untouched",
        },
        "v1_manifest_sha256": v2.sha256_bytes((root / V1_MANIFEST_PATH).read_bytes()),
        "v2_manifest_sha256": v2.sha256_bytes((root / V2_MANIFEST_PATH).read_bytes()),
        "v3_manifest_sha256": v2.sha256_bytes((root / V3_MANIFEST_PATH).read_bytes()),
        "supersedes_v3_because": list(SUPERSEDES_V3_BECAUSE),
        "v3_fixtures_refused": v3_fixtures_refused(),
        "api": api_facts(root),
        "pinned_api_files": {rel: v2.sha256_bytes((root / rel).read_bytes()) for rel in (
            "tests/api/frozen_api_snapshot.json", "tests/api/full_api_snapshot.json",
            "tests/api/v2_frozen_api_snapshot.json", "tests/api/v2_full_api_snapshot.json",
            SURFACE_PATH)},
        "audit": {
            "document": "docs/audits/CORE_REAUDIT_2026-09-16.md",
            "measurements": "benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json",
            "problems": 75, "improvements": 31,
        },
        "certificate": {"required_areas": list(REQUIRED_CERTIFICATE_AREAS),
                        "issued_by": "the recertify workflow's certificate-only child"},
        "capability_claim": CAPABILITY_CLAIM,
        "non_claims": list(NON_CLAIMS),
        "references": {
            "audit": "docs/audits/CORE_REAUDIT_2026-09-16.md",
            "policy": "docs/CORE_FREEZE_POLICY.md",
            "report": REPORT_PATH,
            "verifier": "tools/certification/core_freeze_v4.py",
            "deep_surface_tool": "tools/certification/api_surface_v4.py",
            "manifest_tests": "tests/test_core_freeze_v4_manifest.py",
            "mutation_population": "tests/mutation_population_v4.py",
            "mutation_runner": "tools/certification/mutation_v4_runner.py",
            "superseded_v3_verifier": "tools/certification/core_freeze_v3.py",
        },
    }


def verify(root: pathlib.Path, *, require_clean: bool = True, require_assurance: bool = True) -> v2.Verification:
    from engcore import api_snapshot
    from tools.certification import core_certificate as cc
    from tools.certification import core_freeze as v1

    manifest_file = root / MANIFEST_PATH
    if not manifest_file.exists():
        verification = v2.Verification(mode="NO_MANIFEST")
        verification.add("manifest.present", False, MANIFEST_PATH)
        return verification
    manifest = json.loads(manifest_file.read_bytes())
    head = v2.git(root, "rev-parse", "HEAD")
    candidate = manifest.get("freeze", {}).get("candidate_commit", "")
    exact = head == candidate
    descends = descends_from(root, candidate, head)
    v = v2.Verification(mode="EXACT_FREEZE" if exact else ("DESCENDANT" if descends else "UNRELATED"))
    v.add("manifest.schema", manifest.get("schema") == MANIFEST_SCHEMA, manifest.get("schema"))
    clean = v2.git(root, "status", "--porcelain") == ""
    v.add("tree.clean", clean or not require_clean, "" if clean else "uncommitted changes")
    v.add("tree.relation", v.mode in ("EXACT_FREEZE", "DESCENDANT"),
          f"candidate {candidate[:12]}, HEAD {head[:12]}")

    # R-65: a freeze that does not descend from the previous one is a fork.
    v3_commit = manifest.get("freeze", {}).get("descends_from_v3_commit", "")
    from_v3 = descends_from(root, v3_commit, candidate or head)
    v.add("v4.descends_from_v3", from_v3, f"V3 freeze {v3_commit[:12]}")
    for label, path, key in (("v1", V1_MANIFEST_PATH, "v1_manifest_sha256"),
                             ("v2", V2_MANIFEST_PATH, "v2_manifest_sha256"),
                             ("v3", V3_MANIFEST_PATH, "v3_manifest_sha256")):
        v.add(f"{label}.history_unchanged",
              v2.sha256_bytes((root / path).read_bytes()) == manifest.get(key),
              f"{path} is a record of its own commit and is never rewritten")
    v1_result = v1.verify(root, require_clean=require_clean)
    v1_checks = {check.name: check for check in v1_result.checks}
    v.add("v1.verifier_runs", bool(v1_checks), f"Core Freeze V1 verifier mode {v1_result.mode}")
    # V1's own contract.api check compares the LIVE digest with the one V1 recorded, and this round
    # moved it additively. That is exactly what this freeze is for, so the claim is made HERE, over
    # the stored bytes, and V1's check is reported rather than required.
    v.add("v1.contract_api_is_superseded_additively",
          not api_facts(root)["additive_only_problems"],
          "every difference from the V1 surface as V1 committed it is additive", binding=True)

    # R-69: the comparison is against the stored bytes, and the live surface is the pinned one.
    stored = stored_v1_frozen_snapshot(root)
    v.add("api.stored_v1_bytes_are_v1s_own",
          stored["file_sha256"] == json.loads((root / V1_MANIFEST_PATH).read_bytes())
          ["api"]["pinned_files"][V1_FROZEN_SNAPSHOT_FILE],
          f"{V1_FROZEN_SNAPSHOT_FILE} at {stored['commit'][:12]}")
    facts = api_facts(root)
    problems = facts["additive_only_problems"] + facts["v2_additive_only_problems"]
    v.add("api.additive_only", not problems, "; ".join(problems[:4]) or
          "no non-additive difference from either stored surface")
    v.add("api.enum_insertions_are_recorded",
          manifest.get("api", {}).get("v2_enum_insertions") == facts["v2_enum_insertions"],
          f"{sum(len(e['inserted_before_an_existing_member']) for e in facts['v2_enum_insertions'].values())} "
          f"member(s) inserted before an existing member, each named in the manifest (R-69, finding 95)")
    v.add("api.manifest_records_this_comparison", manifest.get("api") == facts,
          "the manifest's API facts are recomputed and compared, never read")
    pinned = {rel: v2.sha256_bytes((root / rel).read_bytes()) for rel in manifest.get("pinned_api_files", {})}
    v.add("api.pinned_files", pinned == manifest.get("pinned_api_files"),
          "the four snapshots and the deep surface are the bytes this freeze recorded")
    v.add("api.deep_surface_is_the_live_one",
          surface.canonical_bytes() == surface.canonical_bytes(
              json.loads((root / SURFACE_PATH).read_text(encoding="utf-8"))),
          f"{surface.build()['method_count']} method signatures and every enum member's position")

    # R-70: the supersession names its rule.
    refusal = v3_fixtures_refused()
    v.add("v4.v3_fixtures_refused_by_the_named_rule", refusal["refused"],
          f"{refusal['exception']}: {refusal['message'][:120]}")
    v.add("v4.the_refusal_is_recorded", manifest.get("v3_fixtures_refused") == refusal,
          "the manifest's recorded refusal is re-derived, not read")

    certificate = cc.load_certificate(root / "certification/current_core_v2.json")
    result = cc.verify_certificate(root, certificate, require_clean=False, require_commit=False)
    areas = certificate.get("manifest", {}).get("areas", {})
    v.add("certificate.verifies", bool(result.ok),
          "; ".join(result.problems[:3]) if not result.ok else "")
    missing = sorted(set(REQUIRED_CERTIFICATE_AREAS) - set(areas))
    v.add("certificate.covers_required_areas", not missing, f"missing {missing}")
    v.add("certificate.harness_area_covers_what_its_suites_import",
          not cc.harness_pinning_problems(root),
          "derived from the harness TARGETS and the V4 population's target tests (R-68)")

    assurance_file = root / ASSURANCE_PATH
    if assurance_file.exists():
        assurance = json.loads(assurance_file.read_bytes())
        v.add("assurance.schema", assurance.get("schema") == ASSURANCE_SCHEMA)
        v.add("assurance.manifest_sha256",
              assurance.get("manifest_sha256") == v2.sha256_bytes(manifest_file.read_bytes()))
        v.add("assurance.candidate_matches", assurance.get("candidate_commit") == candidate)

        history_problems = _historical_assurance_problems(root, assurance)
        v.add("assurance.history_unchanged", not history_problems,
              "; ".join(history_problems[:3]) or
              "the V4 assurance bytes and measured-commit parentage are unchanged")

        # R-66 still re-derives the historical record so drift is visible, but on a DESCENDANT
        # this is informational: the record describes the 589-mutant tree it measured, while the
        # live descendant may intentionally carry a larger population.  Binding the old population
        # to every descendant made a freshly certified 680-mutant tree fail because history was
        # being compared with the present.  Current-tree mutation evidence is owned by the current
        # certificate/recertification record; the binding V4 obligation here is that the historical
        # assurance itself has not been rewritten.
        logs = {}
        for index, relative in (assurance.get("transcripts") or {}).items():
            path = root / relative
            if path.is_file():
                logs[int(index)] = path.read_bytes()
        mutation_problems = v4_mutation_problems(root, assurance.get("mutations", {}).get("v4", {}),
                                                 logs=logs or None)
        v.add("assurance.v4_mutations_re_derived", not mutation_problems,
              "; ".join(mutation_problems[:4]) or
              f"{len(logs)} transcript(s), every verdict and digest recomputed",
              binding=False)
        suites = assurance.get("suites", {})
        missing_suites = [suite for suite in REQUIRED_V4_SUITES if suite not in suites]
        red = [suite for suite, record in suites.items()
               if suite in REQUIRED_V4_SUITES and not record.get("green")]
        v.add("assurance.required_suites_green", not missing_suites and not red,
              f"missing {missing_suites} red {red}")
        v.add("assurance.measured_commit_is_this_history",
              subprocess.run(["git", "merge-base", "--is-ancestor",
                              assurance.get("measured_commit", "HEAD"), head],
                             cwd=root).returncode == 0,
              f"measured {str(assurance.get('measured_commit'))[:12]}")
    else:
        v.add("assurance.present", False,
              "no assurance record yet: a CANDIDATE, not a completed freeze", binding=require_assurance)
    return v


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--assure", action="store_true",
                        help="write the assurance record from the round's transcripts and the suites")
    parser.add_argument("--no-suites", action="store_true", help="with --assure: skip the suite runs")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--candidate", default="")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--no-assurance", action="store_true")
    args = parser.parse_args(argv)
    root = cc_root()
    if args.build:
        candidate = args.candidate or v2.git(root, "rev-parse", "HEAD")
        manifest = build_manifest(root, candidate)
        path = root / MANIFEST_PATH
        path.write_bytes((json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
        print(f"wrote {MANIFEST_PATH} for candidate {candidate[:12]}")
        problems = manifest["api"]["additive_only_problems"]
        print(f"additive-only problems: {len(problems)}")
        for problem in problems[:20]:
            print(f"  {problem}")
        return 1 if problems else 0
    if args.assure:
        record = build_assurance(root, run_suites=not args.no_suites)
        path = root / ASSURANCE_PATH
        path.write_bytes((json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
        red = [name for name, suite in record["suites"].items() if not suite["green"]]
        print(f"wrote {ASSURANCE_PATH}: {len(record['transcripts'])} transcript(s), "
              f"{record['mutations']['v4']['population']} mutations, red suites {red}")
        return 1 if red else 0
    result = verify(root, require_clean=not args.allow_dirty, require_assurance=not args.no_assurance)
    print(result.render())
    return 0 if result.ok else 1


def cc_root() -> pathlib.Path:
    from tools.certification.core_certificate import repo_root

    return repo_root(pathlib.Path.cwd() / "x")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
