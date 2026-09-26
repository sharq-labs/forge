# Forge solver providers (BIG 11)

**Status:** current provider map. External providers compute; Forge keeps authority over
identity, applicability, materials/data, units, time, state, provenance, uncertainty,
admission and evidence. Every status below comes from a run in the BIG 11 session
(2026-09-26); see `docs/work/PROGRESS.md` for commands and numbers.

```text
Forge scientific model
  -> provider-neutral contract (engcore.providers, engcore.pde.cases, engcore.materials.fluids, ...)
  -> provider adapter (separate distribution under providers/)
  -> external OSS solver/library (in-process library, or argv-only process boundary)
  -> raw result -> Forge normalization -> Forge records (ProviderExecutionRecord, BIG 7 fields, FluidPropertyRecord)
  -> existing admission / provenance / trust pipeline (unchanged)
```

## Provider map

Legend: **EXECUTED** = really run in this environment with tests passing; **CONTRACT ONLY**,
**UNAVAILABLE**, **NOT RUN** otherwise.

```text
Forge
├── Numerical
│   ├── NumPy (dense LU)          EXECUTED (BIG 6)
│   ├── SciPy (root/ODE/linear)   EXECUTED (BIG 6; ODE path corroborates OpenModelica, BIG 11)
│   ├── PETSc (petsc4py KSP)      EXECUTED inside FEniCSx; the standalone BIG 6 PETSc provider NOT RUN
│   └── SUNDIALS                  CONTRACT ONLY
├── PDE/FEM
│   └── FEniCSx 0.11.0            EXECUTED (BIG 8/9/10/11)
├── Coupling
│   └── preCICE 3.4.0             EXECUTED (BIG 9)
├── Battery
│   └── PyBaMM 26.8.0.0           EXECUTED (library)
├── Chemistry
│   └── Cantera 3.2.0             EXECUTED (library)
├── Thermophysical
│   └── CoolProp 8.0.0            EXECUTED (library; conda 6.7.0 replaced by pip during the TESPy install)
├── Thermal systems
│   ├── TESPy 0.11.2              EXECUTED (library; uses CoolProp internally)
│   └── OpenModelica 1.27.1       EXECUTED (process; lumped thermal-capacitance family only)
├── Structural
│   ├── CalculiX 2.23             EXECUTED (process)
│   └── Code_Aster 18.1.7         EXECUTED (process; displacement only)
└── CFD
    ├── OpenFOAM v2412            EXECUTED (process; 2-D lid-driven cavity family only)
    ├── SU2 8.5.0                 EXECUTED (process; 2-D lid-driven cavity family only)
    └── Elmer                     UNAVAILABLE (no conda-forge package; no sudo for apt here)
```

Discovery: `python -m engcore.providers [--json]` lists every known adapter with
availability, version and descriptive capability, in id order. It never ranks and never
selects. `ProviderRegistry.require(id, version=...)` returns exactly that provider or
raises `ProviderUnavailable`; there is no fallback.

## License / deployment matrix

Engineering and deployment planning only; this is not legal advice. The license column
quotes the metadata recorded by the installed package (conda-forge `conda-meta/*.json`,
or pip metadata where installed by pip) in this environment.

| Provider | Version | License (recorded metadata) | Mode | Forge links it? | Redistribution / deployment notes | Recommended boundary |
|---|---|---|---|---|---|---|
| PyBaMM | 26.8.0.0 | BSD-3-Clause (pip metadata text) | Python library | imported by `forge_pybamm` only | permissive; casadi is LGPL-3.0-or-later | optional provider distribution `forge-pybamm-provider` |
| Cantera | 3.2.0 | BSD-3-Clause | Python library | imported by `forge_cantera` only | permissive; mechanisms (e.g. GRI-Mech 3.0) carry their own terms | optional provider distribution |
| CoolProp | 8.0.0 (pip) / 6.7.0 (conda) | MIT | Python library | imported by `forge_coolprop` only | permissive; EOS references are per fluid | optional provider distribution |
| TESPy | 0.11.2 | MIT (pip classifier) | Python library | imported by `forge_tespy` only | permissive; depends on CoolProp | optional provider distribution |
| CalculiX | 2.23 | GPL-2.0-or-later | external process | no (argv process) | ship separately; do not link | process boundary, separate install |
| Code_Aster | 18.1.7 | GPL-3.0-only AND CECILL-C AND Apache-2.0 AND LGPL-3.0-only | external process | no | ship separately; compound license | process boundary, separate install |
| OpenFOAM (openfoam.com) | v2412 | GPL-3.0-only | external process | no | ship separately; do not link | process boundary, separate install |
| SU2 | 8.5.0 | GPL-2.0-or-later (conda-forge build; upstream source LGPL-2.1) | external process | no | ship separately | process boundary, separate install |
| OpenModelica | 1.27.1 | LicenseRef-OSMC-PL | external process | no | OSMC-PL terms must be reviewed before redistribution | process boundary, separate install |
| FEniCSx (dolfinx / basix / ufl) | 0.11.0 / 0.11.0 / 2026.1.0 | LGPL-3.0-or-later / MIT / LGPL-3.0-or-later | Python library | imported by `forge_fenicsx` only | dynamic-link style use from Python | optional provider distribution (conda env) |
| PETSc | 3.23.5–3.25.5 | BSD-2-Clause | library (via FEniCSx) | indirectly | permissive | with FEniCSx |
| preCICE / pyprecice | 3.4.0 | LGPL-3.0-or-later | library + separate processes | imported by `forge_precice` only | dynamic-link style | optional provider distribution |
| Gmsh | 4.15.2 | GPL-2.0-or-later | Python API (`gmsh`) | imported by `engcore.spatial.providers` lazily | GPL: keep optional; Forge core must not require it | optional extra `mesh` |
| meshio | 5.3.5 | MIT | Python library | optional extra `mesh` | permissive | optional extra |
| Elmer | — | not installed | — | — | — | UNAVAILABLE here |

## Optional dependencies

The base `crafty` package imports none of the above. Every adapter is a separate
distribution under `providers/<name>/` with its own `pyproject.toml`. Its heavy
library is imported inside functions, so the adapter imports cleanly without its
stack and reports `ProviderUnavailable`. `tests/test_provider_boundary.py` checks
this for all nine BIG 11 adapters in the core venv. Process solvers are not Python
dependencies at all; their executables are discovered under an explicit provider
prefix (`FORGE_PROVIDER_ENVS`).

## Rules the adapters follow

* Capability is descriptive (`descriptive_capability_not_applicability`). No adapter
  decides scientific applicability; the adapters with bounded case families refuse
  outside their declared bounds (for example the laminar Reynolds bound).
* Execution identity is built from content: the Forge problem, the generated provider
  configuration (decks, dictionaries, `.cfg`, `.mo`, PyBaMM parameter-set digest,
  Cantera mechanism bytes), inputs, window, environment and state, plus the provider
  version and package or executable digest. Result-changing dependencies are part of
  identity: declared Python dependencies (PyBaMM: casadi, pybammsolvers; TESPy:
  CoolProp) by distribution RECORD digest, and process providers by a digest of
  their conda environment's package set. A generated file that names a random
  workspace path is not identity: the Code_Aster `.export` uses workspace-relative
  paths.
* Process providers run with argv only, in a fresh workspace, under an explicit
  environment and a timeout. The executable is re-hashed at launch and refused if it
  changed since discovery. An output counts only if this run created or changed it
  as a regular file (a symlink is never an output), and it is digest-verified when
  read. Exit code 0 is never success on its own.
* Results are `provider_computation_not_evidence` with UNKNOWN uncertainty. A failed
  execution exposes no outputs.
* Cross-provider comparison (`compare_providers`) takes two execution RECORDS
  (provider records, or Forge-internal BIG 6 / BIG 8 records); stand-in objects are
  refused. Values and units are read from the records through a declared,
  digest-bound `OutputSelection` (rows, component, linear weights such as a corner
  average); the caller passes no numbers. It refuses the same provider twice, any
  pair that shares a declared dependency or an identical provider environment (so
  TESPy is never compared against CoolProp), and any side that declares no
  dependency set (independence UNKNOWN, not assumed). An absolute
  tolerance is a spread (0.5 degC is 0.5 K), and a relative tolerance on an
  offset-scale unit is refused. The compared values are digest-bound. A comparison
  whose region was chosen after looking at the data carries `post_hoc=True` and
  is classified `post_hoc_solver_corroboration_not_validation`. Agreement is
  otherwise `solver_corroboration_not_validation`, never validation.
* CoolProp: the reference state is process-global in CoolProp, so the adapter re-pins
  `DEF` on every call and records it. A state outside the equation of state's
  Tmin/Tmax/pmax is an UNKNOWN record. Transport correlations can have narrower
  ranges that this check does not see.
* OpenFOAM: the pressure output is kinematic (p/rho, m2/s2) and defined up to a
  constant (pRefCell 0, pRefValue 0). The end state is called steady only under a
  declared `steady_tolerance`, and a run that misses it fails.
* A state contract lists evolved state that is reset by declaration at every
  execution (`reset_state`). The PyBaMM fast system resets cell temperature and
  particle concentration profiles, so completeness never hides them.
