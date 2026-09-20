# Forge

A scientific simulation runtime: the layer that lets an AI agent state an
engineering problem, run real physics on it, and get back a result that
carries its own provenance, validity assessment and validation evidence —
never a bare number.

Forge is not a solver and does not compete with one. It is the runtime
*around* solvers: a universal problem IR, explicit model-validity semantics,
a strict separation of scientific model / computational realization / solver /
external provider, cross-domain coupling, and evidence-backed validation. New
domains are added as consumers of that core, never by editing it.

## What a result is

Every result a domain produces is a `ScientificResult` that carries:

| Part | What it answers |
|---|---|
| `values` | the quantities, with units |
| `provenance` | which model, which realization, which solver, which version, which settings |
| `validation` | which checks ran, which passed, and which evidentiary level they establish (`dimensionally_valid` → `numerically_converged` → `analytically_verified` → `benchmark_validated` → `cross_solver_validated` → `experimentally_validated`) |
| model `validity` | whether the inputs sit inside the model's declared validity domain: `in_domain`, `outside_validated_domain`, or `unknown` |
| model `validity_not_assessed` | for a declared model nobody asked about: **why not**, in words. A result cannot be constructed that declares a model and says neither |

Three rules make this honest: a validation level is *derived* from a passing check that declares it, never asserted; a model with no declared validity conditions is `unknown`, not valid; and a model that went unassessed is *said* to have gone unassessed, with a reason, rather than being left to be inferred from an empty field. The third one is a rule of the core rather than a convention of the domains — a result that is silent about a model it declares raises at construction, so a domain cannot omit the answer and a reader never has to guess whether an empty mapping means "nobody asked" or "asked and found nothing".

The verification and validation (V&V) layer in `src/engcore/mcp/` collects those judgements into a **credibility evidence report** — credibility in the sense ASME V&V 10/20/40 and NASA-STD-7009 use the word — and derives one advisory verdict from them. It is input to an engineer of record, not a decision, and the project claims no certification or standards conformance. See [docs/mcp/README.md](docs/mcp/README.md).

## Layout

```
src/engcore/
  scientific/    universal core: problem IR, capabilities, models, realizations,
                 solvers, results, provenance, validation, units
  domains/       electrical/ (DC, materials, ngspice provider)
                 thermal/ (1-D conduction — frozen, experiment-pinned)
                 thermal_models/ (lumped capacity, scheme realizations, bulk capture)
                 kinetics/ (CSTR)
  systems/       electrothermal/ (closed-loop electro-thermal coupling)
                 aerospace/multirotor/ (reference design study)
  credibility/  V&V credibility reports and the bridge into SRIA evidence
  sria/          evidence records, admission, assurance, decision and campaigns
  claims/        scientific-intelligence orchestration: claim, routing, planning,
                 evidence requirements, assessment and analysis
  mcp/           external MCP transport/tools; legacy credibility imports are shims
  design/        design generation and design memory
  inference/ uq/ adequacy/ data/
tests/           the suite, tiered (see docs/TESTING.md)
experiments/     frozen, SHA-pinned experiments — inputs to the evidence docs
docs/
  CRAFTY_ARCHITECTURE_CONTEXT.md   architecture, science and product context
  TESTING.md                       how to run the suite
  mcp/README.md                    what the credibility evidence report claims,
                                   and what it does not
  SRIA.md                          what src/engcore/sria/ is, and why nothing
                                   else imports it
  milestones/                      one prereg + freeze/evidence pair per milestone
  architecture-study/              MOOSE, PETSc, OpenFOAM, preCICE, FEniCSx, OpenMDAO studies
```

### Layer boundaries

The frozen Scientific Core is protected by executable import-direction tests. Non-Core layers sit above it: domains and systems provide science, `credibility/` owns V&V report semantics, SRIA owns evidence/assurance authority, `claims/` orchestrates scientific claims, and `mcp/` is the external transport boundary.

A repository invariant now enforces that **`claims` never imports `mcp`**. MCP can call claims; scientific reasoning cannot call back into its transport adapter. The old `engcore.mcp.evidence` and `engcore.mcp.sria_bridge` paths remain identity-preserving compatibility shims for the canonical implementation in `engcore.credibility`.

See [docs/architecture/README.md](docs/architecture/README.md) for the current layer map and [docs/SRIA.md](docs/SRIA.md) for the assurance layer.

## Where this stands

Measured on the adversarial benchmark in `benchmarks/hard/` — 2000 cases,
split 1400 development / 600 sealed hold-out. **The hold-out was opened once,
on 2026-09-08**, and both columns below come from the same tree in the same
session, so they differ in nothing but which cases they contain.

| | dev split (1400) | **hold-out (600)** |
|---|---|---|
| Exact verdict match | 1342/1400 (95.9%) | **579/600 (96.5%)** |
| Catch rate (unsound cases refused) | 1157/1159 (99.8%) | **498/499 (99.8%)** |
| False accept (unsound case reported sound) | 2/1159 (0.17%) | **1/499 (0.20%)** |
| False reject (sound case refused) | 0/241 (0.0%) | **0/101 (0.0%)** |

**The two agree, and that is the point of the hold-out.** The generator behind
these cases has been corrected five times in response to what scoring the
development set revealed, so every development figure is one it was tuned
against. These 600 cases were never scored during any of that. The tool scores
0.6 points *better* on the ones nobody looked at.

Read it narrowly: it says the development figures are not an artifact of the
benchmark having co-evolved with the tool. It does not say the tool is good at
what a human designer would call hard — these are generated cases placed
0.2%–20% from declared bounds, and `benchmarks/ai_designs/RESULTS.md` explains
why that is a different test from a design somebody actually wrote. **The seal
is now spent**: a fresh untuned figure requires a fresh draw.

```bash
python benchmarks/hard/score_hard.py --src src --cases benchmarks/hard/cases_hard --workers 4 --split dev
```

## Working evidence

Each item is preregistered and frozen in `docs/milestones/`, with the tests
that reproduce it.

- **Electrical DC** — models, materials, realizations, and an **ngspice
  provider** that can replace the native solver inside a coupled run, with
  physical admission checks on provider output before it enters coupling.
- **Thermal 1-D conduction** — analytically verified against a closed-form
  reference; scheme realizations (explicit/implicit) of the same model.
- **Closed-loop electro-thermal coupling** — fixed-point coupling with its own
  convergence type, kept distinct from numerical convergence and from
  scientific validity.
- **Kinetics (CSTR)** — cross-solver validation, grid inference with
  admissibility, predictive UQ, and held-out model-adequacy competition.
- **Multirotor** — a system-level reference design study on top of the core.

## Running

```bash
pip install -e ".[dev]"
python -m pytest -m "not expensive" -q -n auto   # FAST       — every edit
python -m pytest -m "not campaign"  -q -n auto   # SCIENTIFIC — after core changes
python -m pytest -q                              # FULL       — before a freeze
```

## Natural-language vertical slice

The MCP server also exposes `plan_engineering_problem`,
`compile_engineering_problem`, `run_engineering_problem` and
`answer_engineering_problem`. They are the first
narrow language-to-evidence path. A deterministic router selects the
electro-thermal or battery boundary only when the user's own domain terms make
one choice unambiguous; generic or tied descriptions return `needs_system`
instead of being forced into a model. Controlled Arabic or English
electro-thermal descriptions can be extracted directly, and either registered
system can be completed with exact declarations before it enters the same case
boundary used by a hand-authored payload. The required physical declarations
for both electro-thermal and battery cases can also be extracted directly from
controlled Arabic or English prose; generated component IDs are disclosed as
non-physical assumptions.

The compiler never fills a physical value from an example.  An incomplete
description returns `needs_input` with one question per missing declaration,
including the expected dimension and an example unit.  Every extracted value
records its source text and span; a complete case is checked by the ordinary
unit and shape boundary before it may run. Optional declarations are also
read from the live model registry: the intent reports which absent inputs
would unlock still-undecidable validity conditions, and understands when an
alternative input has already unlocked the same condition. This is a bounded
interface over the two registered systems, not yet a general model-selection
planner or a general multiphysics graph.

The answer tool adds a stable engineering-facing envelope without replacing
the evidence record. For each component it groups values, the unchanged
verdict, model applicability and exclusions, validation checks, attained
levels and provenance. Predictive uncertainty that was not produced is stated
as `not_quantified` with no intervals; absence is never presented as zero
uncertainty. The complete execution response remains attached for audit.

`answer_engineering_scenarios` is the first uncertainty path over these
systems. The caller supplies 2–100 named declaration scenarios on a common
base; Forge runs every one through the ordinary evidence boundary and reports
unit-aware min/max envelopes for outputs present in every scenario. These are
explicitly non-probabilistic bounds: no confidence level or distribution is
attached, and the response lists observation noise, model-form uncertainty,
unexplored input space and residual numerical error among what it does not
cover. A scenario outside model validity remains visible beside the bounds.

`evaluate_engineering_context` evaluates explicit output criteria such as
`R1.final_temperature <= 350 kelvin`, using either a point result or a scenario
envelope. Numerical satisfaction and evidential credibility are separate:
a threshold can be numerically satisfied while the decision remains
`indeterminate_evidence`, and an envelope crossing the threshold returns
`indeterminate_uncertainty`. The evaluation is advisory and does not claim
certification.

`answer_engineering_uncertainty` propagates caller-declared uniform or normal
input distributions with deterministic stratified Latin-hypercube samples.
The caller must explicitly declare `dependence="independent"`; correlated
inputs are refused until a correlation model is implemented. Every equal-mass
sample crosses the ordinary validity and evidence boundary. If any sample is
not `SUPPORTED`, no predictive interval is emitted: the tool reports
`predictive_support_not_admitted` rather than silently conditioning on the
survivors. Successful results carry empirical central intervals, mean,
standard uncertainty, sample count and stated exclusions including model-form
uncertainty.

## Development discipline

- A milestone starts with a preregistration (`*-prereg.md`) that states the
  hypothesis, the proofs, and the fail conditions, and ends with a freeze or
  evidence document. Tests map to preregistered proofs.
- Frozen experiments pin their inputs by SHA-256 over raw bytes. Pinned trees
  are not edited or extended without a re-freeze (`.gitattributes` forces LF
  for this reason).
- Domain-specific conditionals in `scientific/` are treated as an
  architectural failure, and a test asserts it.

History: the Bayesian-optimizer research line that preceded Forge was removed
from the tree in September 2026 and remains in git history under the tag
`archive/optimizer-research-v0.3.4`.
