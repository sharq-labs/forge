"""Dimensions A and B: required inputs, and UNKNOWN-unless prerequisites.

The Contract Integrity round already built the two hard parts of this: a
machine-readable claim map that says which declarations each published
"UNKNOWN unless ..." clause is talking about, and a set of nominal contexts
per system that can be assembled with any declaration withheld. It ran them
once, as an audit, and wrote the answer to JSON.

An audit that ran once protects nothing. This module re-runs that same
machinery live, so the answer is recomputed from the current tree every time
the guards execute. Three regressions then fail a test instead of ageing
quietly inside a results file:

* a record's stated prerequisite stops being one (the assembler starts
  producing the quantity without it) -- RECORD_TOO_BROAD;
* a route the record advertises as an alternative stops working alone --
  RECORD_TOO_NARROW;
* a condition ships with no entry in the claim map at all, which is how a new
  model would otherwise arrive unguarded.

Nothing here writes to the Contract Integrity artifacts. They are read-only
inputs to this round, and their recorded results stand as they were.
"""

from __future__ import annotations

import functools
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
CONTRACT_INTEGRITY_AUDIT = REPO / "benchmarks" / "contract_integrity" / "audit"


def _audit_module(name: str):
    """Import one Contract Integrity audit module without disturbing the tree."""
    path = str(CONTRACT_INTEGRITY_AUDIT)
    if path not in sys.path:
        sys.path.insert(0, path)
    return __import__(name)


@functools.lru_cache(maxsize=1)
def unknown_promise_review() -> dict:
    """Every published UNKNOWN-unless clause, re-checked against the runtime."""
    review = _audit_module("review")
    result = review.review()
    rows = result["rows"]
    return {
        "checks": len(rows),
        "conditions_reviewed": len(result["reviewed_pairs"]),
        "disagreements": [row for row in rows if row["result"] != review.MATCH],
        "rows": rows,
    }


#: Later rounds add conditions, and the claim map that must speak for them is
#: a result artifact of the round that wrote it. Rather than edit an earlier
#: round's file, a round registers its own entries here and they are merged.
#: The guard is unchanged in force: a condition in no map at all still fails.
SUPPLEMENTS = (
    (
        "benchmarks.capability_boundary.audit.claim_map_supplement",
        "SUPPLEMENT",
    ),
)


@functools.lru_cache(maxsize=1)
def all_claims() -> dict:
    """The Contract Integrity claim map plus every later round's supplement."""
    import importlib

    claims = dict(_audit_module("claim_map").CLAIMS)
    for module_name, attribute in SUPPLEMENTS:
        try:
            module = importlib.import_module(module_name)
        except ImportError:  # pragma: no cover - a round removed, not renamed
            continue
        claims.update(getattr(module, attribute))
    return claims


@functools.lru_cache(maxsize=1)
def claim_map_coverage() -> dict:
    """Which shipped conditions the claim map speaks for, and which it misses."""
    from . import records

    claims = all_claims()
    mapped = set(claims)
    shipped = {(ref.system, ref.name) for ref in records.conditions()}
    return {
        "shipped": sorted(shipped),
        "unmapped": sorted(shipped - mapped),
        "mapped_beyond_surface": sorted(mapped - shipped),
    }


@functools.lru_cache(maxsize=1)
def required_input_survey() -> dict:
    """Does ``required`` in a record mean required at the public constructor?

    Driven by the live records rather than by the frozen surface snapshot, so
    an input marked required tomorrow is probed tomorrow.
    """
    from . import records

    from .constructors import probe
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    baseline = {}
    for model in records.shipped_models():
        system = records.system_of(model.model_id)
        if system not in baseline:
            baseline[system] = probe(system, None)
        for spec in model.inputs:
            if spec.source_kind.value == "variable" and spec.role is None:
                # A solved unknown with no role is an output of the analysis.
                # "Required" there means the result is not complete without it,
                # not that a caller supplies it, so there is no constructor to
                # probe. A VARIABLE carrying a STATE or CONTROL role is the
                # opposite: an initial condition or a driving input the caller
                # does supply, and it is probed like any other.
                continue
            key = (system, spec.name)
            if key in seen:
                continue
            seen.add(key)
            outcome = probe(system, spec.name)
            refused = outcome.startswith("REFUSED")
            if outcome == "NO_BUILDER":
                result = "NO_PUBLIC_CONSTRUCTOR_PROBE"
            elif outcome == "NOT_A_CONSTRUCTOR_FIELD":
                result = "NOT_CONSTRUCTOR_ADDRESSABLE"
            elif spec.required:
                # Required in the record: the constructor must refuse without it.
                result = "MATCH" if refused else "RECORD_TOO_BROAD"
            else:
                # Optional in the record: the constructor must build without it.
                # This is the direction a caller feels immediately -- a record
                # that says "you may leave this out" and a runtime that will
                # not is a promise broken at the first call.
                result = "RECORD_TOO_NARROW" if refused else "MATCH"
            rows.append(
                {
                    "system": system,
                    "model_id": model.model_id,
                    "input": spec.name,
                    "record_says": "required" if spec.required else "optional",
                    "runtime": outcome,
                    "result": result,
                }
            )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["result"]] = counts.get(row["result"], 0) + 1
    return {
        "baseline_construction": baseline,
        "checks": len(rows),
        "counts": dict(sorted(counts.items())),
        "contradictions": [
            row
            for row in rows
            if row["result"] in ("RECORD_TOO_BROAD", "RECORD_TOO_NARROW")
        ],
        "rows": rows,
    }


#: Phrases a record uses to publish that a condition answers itself -- that it
#: is settled by the model's own declared scope rather than by anything the
#: caller supplies. Kept as an explicit, reviewable list rather than inferred,
#: because "this condition needs no input" is a claim, and a claim needs to be
#: written down somewhere a reader will find it.
SELF_SATISFIED_PHRASES = (
    "satisfied by this model's own scope",
    "not measured from a caller's context",
)


@functools.lru_cache(maxsize=1)
def self_derived_survey() -> dict:
    """Nothing declared must derive nothing -- unless the record says otherwise.

    A domain assembler that produces a quantity from an empty declaration set
    has answered a question the caller never supplied an input for. Every
    condition standing on that quantity then leaves UNKNOWN on evidence that
    does not exist, and every "UNKNOWN unless ..." clause in its record becomes
    false at once -- without any record being edited, so no text comparison can
    see it.

    The one legitimate case is a condition settled by the model's declared
    scope (DC's electrical length: a steady-state model has no frequency, so
    the ratio is identically zero for every circuit). That case is allowed
    precisely when the record says so.
    """
    from . import records

    nominals = _audit_module("nominals")
    by_name: dict[str, list] = {}
    for ref in records.conditions():
        by_name.setdefault(ref.name, []).append(ref)

    rows: list[dict] = []
    for context_id, (_declarations, assemble) in nominals.CONTEXTS.items():
        try:
            produced = assemble({})
        except Exception as exc:
            rows.append(
                {
                    "context": context_id,
                    "quantity": None,
                    "result": f"REFUSED:{type(exc).__name__}",
                }
            )
            continue
        for name in sorted(produced):
            refs = by_name.get(name, [])
            declared = any(
                phrase in (ref.description or "").lower()
                for ref in refs
                for phrase in SELF_SATISFIED_PHRASES
            )
            rows.append(
                {
                    "context": context_id,
                    "quantity": name,
                    "records": [ref.ref for ref in refs],
                    "result": "DECLARED_SELF_SATISFIED" if declared else "UNDECLARED",
                }
            )
    return {
        "contexts": len(nominals.CONTEXTS),
        "undeclared": [row for row in rows if row["result"] == "UNDECLARED"],
        "rows": rows,
    }
