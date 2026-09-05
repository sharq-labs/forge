# Crafty Open-Source Architecture Study Index

**Status:** Research cycle complete — 2026-09-02

This directory supplements `docs/CRAFTY_MASTER_CONTEXT.md`.

For any new ChatGPT / Claude / Codex / human architecture session:

1. Read `docs/CRAFTY_MASTER_CONTEXT.md` first for the full project, scientific, commercial, funding and acquisition context.
2. Read `docs/architecture-study/07_CRAFTY_ARCHITECTURE_SYNTHESIS_V1.md` second for the current architecture synthesis produced after studying mature open-source scientific systems.
3. Inspect the current repository state before implementation.
4. Treat the individual studies below as design evidence and rationale, not code to copy.

## Studies

1. `01_MOOSE_ARCHITECTURE_STUDY.md` — extensible multiphysics/core-domain architecture
2. `02_PETSC_ARCHITECTURE_STUDY.md` — composable numerical solver hierarchy
3. `03_OPENFOAM_ARCHITECTURE_STUDY.md` — mature deep-domain / CFD architecture
4. `04_PRECICE_COUPLING_STUDY.md` — cross-solver multiphysics coupling
5. `05_FENICSX_MFEM_EQUATION_FIELD_STUDY.md` — equation, field, FEM and discretization architecture
6. `06_OPENMDAO_MODELICA_SYSTEM_COMPOSITION_STUDY.md` — multidisciplinary and acausal system composition
7. `07_CRAFTY_ARCHITECTURE_SYNTHESIS_V1.md` — Crafty-native synthesis and recommended milestone sequence

## Current conclusion

The studies reinforce rather than replace Crafty's existing direction.

Immediate implementation milestone remains:

```text
MODEL0-R
Scientific Capability + Scientific Model / Computational Realization separation
```

Do not begin broad domain implementation before MODEL0-R is preregistered, implemented, tested and reviewed.

## Current architecture reference pair

```text
docs/CRAFTY_MASTER_CONTEXT.md
+
docs/architecture-study/07_CRAFTY_ARCHITECTURE_SYNTHESIS_V1.md
```

Together these are the current persistent context for continuing Crafty.

## IP policy

These studies are architectural learning only. Do not copy implementation code from the studied projects into Crafty without an explicit dependency/licensing decision. Crafty contracts and implementations should remain independently designed and attributable.
