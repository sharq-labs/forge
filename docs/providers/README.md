# External scientific providers

**Status: current architecture entry point for `engcore.providers`.**

Forge executes solvers it does not own. This page says where that boundary is,
what it is allowed to do, and what it is structurally prevented from doing.

## Where it sits

```text
Scientific Core -> domains/systems -> credibility -> claims/SRIA -> MCP
                        ^
                        |
                   providers
```

`providers` is an outer boundary in the same sense `mcp` is. It imports the
Scientific Core and the domains; **nothing below it imports it**, and a test
asserts that `credibility`, `claims` and `sria` do not name a provider in code.
It is recorded in `tests/test_core_api_layering.py::NON_CORE_PACKAGES` and in
`docs/CORE_FREEZE_POLICY.md` §2. Nothing in it is exported from a canonical
module, so the frozen digest does not move.

The placement is load-bearing rather than tidy. A Core package that could reach
a provider would be a Core whose importability depended on an optional
third-party wheel, and `engcore.providers` exists partly to make that
impossible.

## The three, and the boundary each carries

| provider | what it computes | what it may NOT be used for | extra |
| --- | --- | --- | --- |
| PyBaMM | battery models and their numerical solution | granting its own support | `forge[battery-pybamm]` |
| PyBOP | parameter fits | validation or holdout data | `forge[battery-fit]` |
| SALib | sensitivity indices | validation evidence | `forge[sensitivity]` |

Each boundary in the third column is enforced by a type, not by a review:

* `PyBOPProvider.execute` refuses every `DatasetRole` except `CALIBRATION`,
  **before PyBOP is imported**. `UNSPECIFIED` is a role and is refused too.
* `SensitivityEvidence.is_validation_evidence` is a property returning `False`,
  with no setter and no corresponding dataclass field, so no constructor
  argument, payload key or subclass can make it true.
* A PyBaMM run produces validation checks that establish **no**
  `ValidationLevel`, and a guard walks `src/engcore/providers/` to keep it that
  way. `tests/domains/test_evidentiary_level_audit.py` covers `domains/**` and
  does not reach this package; that hole is closed by
  `test_no_provider_validation_check_grants_an_evidentiary_level`.

## The contract

Five concepts, in `engcore/providers/contract.py`. They are the four things
that were the same between ngspice and PyBaMM, and nothing else — the
`HETERO-NGSPICE` adapter's own docstring names "a second external provider
whose process-execution needs actually overlap" as the trigger for
generalising, and PyBaMM's do **not** overlap (a subprocess fed a netlist
versus an in-process Python library). So execution is deliberately not
generalised.

| concept | what it answers |
| --- | --- |
| `ProviderIdentity` | which exact external implementation produced this number |
| `ProviderRequest` | what was asked, in Forge's vocabulary, digestible |
| `ExecutionOutcome` | did the provider fail, or was the science declined |
| `ProviderExecutionReceipt` | what ran, including when nothing was produced |
| `ProviderResult` | the answer, or evidence about answers, never both |

A provider that produces a scientific answer produces a **`ScientificResult`** —
the same record the native solvers produce — so credibility, applicability,
validation, uncertainty, claims and certification keep working without knowing
a provider exists.

### The outcome vocabulary

```text
provider side                    Forge side
  PROVIDER_UNAVAILABLE             MODEL_NOT_APPLICABLE
  PROVIDER_ERROR                   FORGE_REFUSED
  NUMERICAL_FAILURE                MISSING_EVIDENCE

              OK  — a result exists to be judged, and nothing more
```

`ExecutionOutcome.is_provider_side` divides them and `OK` is in neither half.
An unimportable package is not evidence against a hypothesis; a model that ran
perfectly and is not applicable here has not failed.

## Applicability precedes execution

`PyBaMMProvider.execute` screens before PyBaMM is called, and the order is not
a performance choice. A solve that has already happened is a number somebody
can read, and screening afterwards produces a result and a refusal at the same
moment.

The screen is `ParameterAuthority.screen`, and it turns on three declared
conditions: chemistry, nominal capacity (within `CAPACITY_TOLERANCE`), and a
temperature band. All failing conditions are reported, not the first.

Two details that were found by running it rather than by designing it:

* **A temperature band names the quantity it is stated against.**
  `ParameterAuthority.temperature_basis` is `"ambient"` or `"cell"`, and
  `CellUnderTest` carries both. The first version screened an ambient against
  a band the open-circuit-voltage authority states on *cell* temperature, and
  refused five low-ambient 4 A trajectories on a quantity the band was never
  about. A cell that cannot supply the authority's basis is refused, never
  given the other temperature as a substitute.
* **A model's own state interval is applicability.**
  `PyBaMMModelSpec.state_of_charge_interval` declares the open interval the
  equivalent-circuit model's charge state lives on. At exactly 1.0 PyBaMM's
  `Maximum SoC` event is non-positive at the initial condition and the solve
  ends before its first step; that reaches a caller as `MODEL_NOT_APPLICABLE`
  rather than as a crash.

## Parameter authority

Every run is governed by a `ParameterAuthority`, and a named PyBaMM parameter
set cannot be edited in place: constructing one with `overrides` is refused,
and `derive()` is the only route, returning a **new** authority whose `source`
is `forge_derived` and which records its parent's digest.

The authority digest is part of the provider identity, so a parameter change
moves the identity of every run that cites it.

## Replay means re-execution

`replay_provider_request` executes the request again and compares canonical
outputs at a tolerance that defaults to `0.0`. It reports `executed`,
`identity_matched` and `reproduced` separately: reproducing the same numbers
under a *different* provider version demonstrates nothing about determinism,
and `drift` names every identity field that moved.

## Optional by construction

No provider is imported at module scope anywhere in this package. Every import
is inside the function that needs it, so `import engcore.providers` succeeds on
a bare install and a request to an absent provider returns
`PROVIDER_UNAVAILABLE` — a result, not an exception.
`tests/providers/test_provider_contract.py::test_forge_imports_without_the_provider_extras`
runs that in a subprocess with the three distributions blocked from the import
system.

### Python version ceiling, recorded rather than worked around

PyBOP 26.3 declares `requires-python = ">=3.10,<3.14"`. This repository supports
`>=3.11`, so on a 3.14 interpreter `forge[battery-fit]` is uninstallable and its
provider reports `PROVIDER_UNAVAILABLE`. The benchmark and the provider tests
were run on a dedicated CPython 3.13.15 environment for that reason; the rest of
the suite runs on 3.14 as before.

## Licensing

`engcore/providers/licenses.py` holds what each distribution's own metadata
states, plus one fact about this repository: `integration_mode` is
`"optional runtime import"` for all three. None is vendored and none is
redistributed. No legal conclusion beyond that is drawn or implied.
