# Scientific Twin V0.1 — preregistration

Status: **FROZEN BEFORE IMPLEMENTATION**

Milestone ID: `TWIN-V0.1`

Starting point: K2 PASS/FROZEN; `main == dev` at `5dceeb4e3ad1437c5c01aa993ac85942989c7c88` before this preregistration commit.

## Purpose

Scientific Twin V0.1 introduces the domain-neutral **scientific system instance contract** that sits between reusable scientific models/data and study-specific virtual experiments.

A twin is an input to scientific studies. It is not a solver, not a posterior, not a result, and not a claim that a physical object has been validated.

The contract must support both systems that already exist and systems that are only hypothetical candidates.

## Architectural position

```text
Scientific Models + typed system data + evidence
                    |
                    v
            Scientific Twin
                    |
                    v
        Scientific Study / Experiment
                    |
                    v
      Solver -> Result -> Evidence
                    |
                    v
        Inference / UQ / Adequacy
                    |
                    v
             Twin successor
```

The twin therefore arrives **before K3/K4 as a stable input boundary**, while K3 and K4 later enrich how uncertainty and model adequacy are represented and used. V0.1 must not pretend those later capabilities already exist.

## Scientific meaning

A `ScientificTwin` is an immutable, versioned declaration of one specific scientific system instance.

It binds:

- stable twin identity and version;
- twin kind;
- one or more versioned `ModelReference`s;
- typed fixed system parameters;
- typed operating/state declarations available to studies;
- assumptions;
- evidence references;
- optional calibration evidence references;
- optional validity-context declarations;
- lineage to a parent twin version;
- metadata that is not allowed to act as a scientific side channel.

All numerical scientific values in the twin must use existing typed Scientific Core value contracts. Bare floats are not accepted as scientific parameter/state values.

## Twin kinds

V0.1 defines:

- `CONCEPT`: incomplete early scientific concept;
- `REFERENCE`: representation of a known/reference system;
- `CANDIDATE`: hypothetical design/system not required to exist physically;
- `CALIBRATED`: a twin whose declared parameter state is backed by explicit calibration evidence;
- `ENSEMBLE`: one system represented by multiple model references;
- `DERIVED`: a successor explicitly linked to a parent twin version.

These kinds describe provenance/role, not truth level.

## Non-negotiable invariants

1. `twin_id` and `version` are non-empty.
2. At least one model reference is required except for `CONCEPT`, which may be structurally incomplete.
3. Model references are unique by `(model_id, version)`.
4. Parameter names are unique.
5. State/operating declaration names are unique.
6. A name may not silently exist as both a fixed parameter and a state declaration.
7. `CALIBRATED` requires at least one explicit calibration evidence reference.
8. `ENSEMBLE` requires at least two distinct model references.
9. `DERIVED` requires a parent reference; non-derived twins may still carry a parent only when explicitly representing a successor version, but serialization must preserve that fact exactly.
10. Metadata is never included in `scientific_context()`; scientific validity/admission must use typed declarations, not metadata.
11. Serialization is deterministic and schema-versioned.
12. Round-trip serialization preserves twin scientific identity exactly.

## Scientific context

V0.1 exposes a typed `scientific_context()` accessor formed only from declared parameters and state/operating declarations. It is intended as the future input to model binding, validity assessment and study materialization.

Metadata is deliberately excluded.

## Evidence boundary

Evidence references in V0.1 are opaque immutable identifiers/URIs only. V0.1 does not implement the future Scientific Artifact Store and does not assert that a string reference is scientifically sufficient by itself.

A later admission/evidence layer will resolve and validate those references.

## Uncertainty boundary

V0.1 does **not** invent a parameter-distribution or calibrated UQ representation before K3.

It may preserve evidence references that later support uncertainty/calibration, but quantified uncertainty is explicitly deferred to K3.

## Study relationship

`ScientificProblem` remains the declaration of *what a study asks to compute*.

`ScientificTwin` declares *what system instance the study is about*.

They must not be collapsed into one type.

A later Study Runtime will bind a twin + study intent/problem + observations/evidence into an executable study.

## Acceptance criteria

T1. Construct valid `CONCEPT`, `REFERENCE`, `CANDIDATE`, `CALIBRATED`, `ENSEMBLE`, and `DERIVED` twins.

T2. Reject blank identity/version and duplicate model references.

T3. Reject bare numeric parameter/state values through the existing typed Scientific Core value boundary.

T4. Reject duplicate parameter names, duplicate state names, and parameter/state name collisions.

T5. Reject `CALIBRATED` without calibration evidence.

T6. Reject `ENSEMBLE` with fewer than two distinct model references.

T7. Reject `DERIVED` without a parent twin reference.

T8. Deterministic `to_dict()` / `to_json()` output and exact schema round-trip.

T9. `scientific_context()` contains typed declared system context and excludes metadata.

T10. Existing regression suite remains green; no frozen K1/K1.5/K2 scientific artifact or preregistration is changed.

## Explicitly out of scope

Scientific Twin V0.1 does not implement:

- online sensor synchronization;
- a traditional live operational digital twin;
- Bayesian state estimation;
- quantified parameter uncertainty (K3);
- model competition/adequacy (K4);
- evidence admission/artifact resolution;
- Scientific Study Runtime;
- autonomous discovery or invention;
- cross-domain coupling;
- physical validation claims.

## Freeze rule

This preregistration is frozen before implementation. If an invariant or acceptance criterion proves wrong, record an explicit deviation rather than silently rewriting this file to match the implementation.
