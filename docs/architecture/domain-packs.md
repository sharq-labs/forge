# Forge Domain Pack v1

A Domain Pack is the atomic installation and activation boundary for one
scientific domain. It is deliberately stricter than a generic plugin system:
the thing being loaded can affect scientific model selection, execution,
evidence and replay, so "installed" must never mean "active".

## Lifecycle

```
installed distribution metadata
        |
        v
DISCOVERED
        |
        | explicit load
        v
LOADED
        |
        | validate manifest <-> runtime agreement
        v
REGISTERED / VALIDATED
        |
        | explicit enable(pack_id, exact_version)
        v
ENABLED
        |
        | explicit planner/experiment selection
        v
USED IN SCIENTIFIC EXECUTION
```

There is no automatic transition from installation or discovery to scientific
authority.

## Why one atomic entry point

External distributions publish one provider factory under the standard Python
entry-point group:

```toml
[project.entry-points."forge.domainpacks"]
battery = "forge_battery:domain_pack"
```

Forge discovers only entry-point metadata. Importing provider code is a
separate explicit operation. Registering the provider validates the entire pack
as one unit, and enabling it is separate again.

We intentionally do not use independent entry points for models, solvers,
validation protocols and UQ producers. Mixing arbitrary versions of those
pieces can create a computationally importable but scientifically incoherent
domain.

## Contract split

### DomainPackManifest

Immutable/digestable declaration of:
- exact pack identity and version;
- compatible Domain Pack API versions;
- provided scientific capabilities;
- model identities;
- realization identities;
- solver identities;
- calibration/validation/UQ/adaptor/transformation/benchmark identities.

The manifest is provenance data. Its digest can be bound into replay records.

### DomainPackProvider

Runtime implementations corresponding to the manifest:
- `models()`;
- `realizations()`;
- `solver_factories()`;
- calibration/validation/UQ providers;
- measurement adapters;
- transformations;
- benchmarks.

The validator compares the manifest against what the provider actually returns.

## Validation rules in v1

Registration fails closed when:
- the pack does not declare the current Domain Pack API;
- model records differ from the manifest;
- a model belongs to a different declared domain;
- realization records differ from the manifest;
- a realization references a model outside the atomic pack;
- capability declarations differ from realization-provided capabilities;
- solver factories fail the Scientific Core solver registry contract;
- auxiliary artifact identities differ from the manifest.

Validation is not evidence that a scientific model is correct. It proves only
that the plugin package is internally coherent with what it declares.

## Deterministic registry

The registry:
- uses exact `(pack_id, pack_version)` identities;
- never resolves `latest`;
- never ranks alternative packs;
- never enables a registered pack automatically;
- lists candidates in deterministic order.

If multiple enabled packs provide the same capability, selection remains an
explicit planner/policy problem rather than a registry side effect.

## Provenance snapshot

`DomainPackSnapshot` records:
- pack id/version;
- domain;
- manifest digest;
- package origin/distribution metadata;
- entry-point identity;
- capabilities;
- exact model/realization/solver identities.

This lets replay distinguish "same model id, different surrounding pack" from
the original environment.

## Built-in Battery Pack

The first pack wraps the existing battery domain without moving its files.

It exposes only currently formal battery artifacts:
- four existing `ScientificModelDefinition` records;
- four existing realizations;
- the existing closed-form battery solver;
- OCV calibration protocols;
- OCV empirical adequacy validation.

The experimental 1RC/Thevenin kernel is deliberately *not* listed as a model
or realization yet. Code existence is not scientific authority. It must first
receive a formal model definition, realization contract and validation path.

The NASA adapter currently lives in the outer claims adapter layer, so the
Battery Pack does not import it. This preserves the dependency direction and
leaves measurement-adapter ownership to a later domain-normalization step.

## External plugin security/trust boundary

Python entry points execute Python code when loaded. Domain Pack discovery
therefore returns metadata descriptors only. Loading an external descriptor is
an explicit action, and a loaded provider is still neither registered nor
enabled until those separate operations occur.

Domain Pack v1 does not claim sandboxing of third-party Python. Organizational
allow-lists/signatures can be added above this contract later; the current
guarantee is that discovery alone imports nothing and scientific activation is
explicit.
