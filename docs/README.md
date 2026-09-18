# Forge Documentation

This directory is the human-facing documentation index for Forge.

## Source-of-truth policy

Documentation explains the implementation; it does not define scientific capability by itself.

When sources disagree, use this precedence:

1. executable scientific contracts in `src/engcore/`;
2. tests and validation gates in `tests/`;
3. reproducible evidence in `benchmarks/`, `experiments/`, and `certification/`;
4. this documentation.

A Markdown claim must never be broader than the code, declared applicability/capability contracts, and evidence that support it.

## Layout

- `architecture/` — **current architecture entry point and layer map**.

- `CORE_FREEZE_POLICY.md` — compatibility/freeze policy used by the certification process.
- `TESTING.md` — developer testing guidance.
- `SRIA.md` — SRIA concepts and architecture.
- `domains/` — domain-specific documentation.
- `assurance/` — assurance and evidence explanations.
- `reviews/` — review records and claim/capability audits.
- `audits/` — dated historical audit snapshots; read its README before treating a finding as current.
- `project/` — project needs and planning material.
- `architecture-study/` — historical/reference architecture studies; not current executable truth.
- `archive/` — superseded historical material.

## Repository hygiene

- Keep the repository root limited to entry-point/project files; long-form Markdown belongs here under `docs/`.
- Do not add Markdown documentation inside `src/`; implementation details belong in docstrings and executable contracts.
- Keep benchmark/campaign reports beside the evidence they describe when their proximity is necessary for reproducibility.
- Do not move certification records out of `certification/` merely to make documentation look tidier.
