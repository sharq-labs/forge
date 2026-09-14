# Forge Architecture Study Index

**Status:** Historical/reference research cycle completed 2026-09-02.

These studies record design research and rationale. They are **not** the current executable architecture contract and must not be used to infer capabilities that are absent from the code, tests, or scientific evidence.

For current work:

1. Start at [`docs/README.md`](../README.md) for documentation/source-of-truth policy.
2. Read [`docs/CRAFTY_ARCHITECTURE_CONTEXT.md`](../CRAFTY_ARCHITECTURE_CONTEXT.md) for the maintained architecture context.
3. Inspect the current repository contracts and tests before implementation.
4. Use the studies below only as historical design evidence and rationale, not as code or current capability declarations.

## Studies

1. `01_MOOSE_ARCHITECTURE_STUDY.md` — extensible multiphysics/core-domain architecture
2. `02_PETSC_ARCHITECTURE_STUDY.md` — composable numerical solver hierarchy
3. `03_OPENFOAM_ARCHITECTURE_STUDY.md` — mature deep-domain / CFD architecture
4. `04_PRECICE_COUPLING_STUDY.md` — cross-solver multiphysics coupling
5. `05_FENICSX_MFEM_EQUATION_FIELD_STUDY.md` — equation, field, FEM and discretization architecture
6. `06_OPENMDAO_MODELICA_SYSTEM_COMPOSITION_STUDY.md` — multidisciplinary and acausal system composition
7. `07_CRAFTY_ARCHITECTURE_SYNTHESIS_V1.md` — historical Crafty-native synthesis from that research cycle

## Interpretation rule

If an architecture study, synthesis document, README, or review disagrees with the current implementation, the implementation contract and its executable evidence win. A study may motivate a future capability; it does not prove that Forge currently has it.

## IP policy

These studies are architectural learning only. Do not copy implementation code from the studied projects into Forge without an explicit dependency/licensing decision. Forge contracts and implementations should remain independently designed and attributable.
