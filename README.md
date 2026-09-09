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
  sria/          evidence records, admission, assurance, decision, campaigns —
                 19,887 lines, 26% of src/, an independent layer that is NOT on
                 the verification path and is imported by nothing else in src/.
                 Read the section below before reading the tree; see docs/SRIA.md
  mcp/           verification and validation (V&V) layer: assembles a
                 credibility evidence report for consumers and derives its
                 advisory verdict
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

### A third of `src/` is not on the verification path

`src/engcore/sria/` is **19,887 lines across 53 modules — 25.6% of the source
tree — and nothing in `src/` outside it imports it.** Verify that in one
command:

```bash
grep -rn "engcore\.sria\|from \.\.sria\|from \.sria\|import sria" --include=*.py src/ | grep -v "^src/engcore/sria/"
```

It returns nothing. The MCP credibility layer, the electro-thermal system, the
battery and kinetics domains and every solver run without it; removing the tree
would leave every domain result, every coupling and every advisory verdict
identical.

That is a statement about **layering, not about worth**. SRIA is an
experimental-campaign, decision and assurance layer that sits one altitude above
the domains: where they answer *what does this system do*, it answers *what
should we measure next, what may change belief, and on whose authority*. It has
its own frozen milestone sequence (M1 through V0.1, plus Core V0.3 and the E1–E3
experiment line) and 630 of the suite's 3,095 tests, two of its test modules
being SHA-256 byte-pinned by frozen experiment configs.

It is called out here rather than only in `docs/SRIA.md` because a reader
opening this repository will meet a third of the code before they meet an
explanation of it. [docs/SRIA.md](docs/SRIA.md) has the full account: what it
was built for, what depends on it, and what separating it would cost.

The package is still named `engcore` because several frozen experiments pin
source paths by SHA-256; it is renamed at the next planned re-freeze.

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
