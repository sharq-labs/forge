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

Two rules make this honest: a validation level is *derived* from a passing check that declares it, never asserted; and a model with no declared validity conditions is `unknown`, not valid.

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
                 an independent layer, NOT on the verification path and imported
                 by nothing else in src/; see docs/SRIA.md
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

The package is still named `engcore` because several frozen experiments pin
source paths by SHA-256; it is renamed at the next planned re-freeze.

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
