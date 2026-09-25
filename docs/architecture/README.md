# Forge Architecture

**Status: current architecture entry point.**

Executable contracts and tests remain the source of truth; this page explains how to navigate them.

## Layer map

```text
Frozen Scientific Core
  scientific -> data -> inference -> uq -> hybrid_uq -> adequacy
                                   execution -> studies
            |
            +-> domains -> systems
                    |
                    v
              credibility
                    |
          +---------+---------+
          |                   |
         SRIA               claims
          |                   |
          +---------+---------+
                    v
                   MCP
```

The load-bearing rule is architectural: **MCP is transport, not scientific authority.** Claims may consume credibility and SRIA, but `engcore.claims` must never import `engcore.mcp`.

## Package responsibilities

- `scientific/` and the other frozen Core packages own reusable scientific contracts and algorithms.
- `domains/` owns domain science; `systems/` composes domains.
- `credibility/` owns credibility reports and translation into SRIA evidence.
- `sria/` owns evidence admission, assurance, campaign and decision authority.
- `claims/` owns scientific-intelligence orchestration: claim contracts, routing, planning, evidence requirements, assessment and analysis.
- `mcp/` is the external tool/transport boundary. Old credibility import paths remain compatibility shims.
- Non-Core BIG 2-10 layers (all registered in `tests/test_core_api_layering.py::NON_CORE_PACKAGES`):
  `scenarios/` (BIG 2 time engine, BIG 3 environment, BIG 4 lifecycle), `materials/` (BIG 5),
  `numerical/` (BIG 6), `spatial/` (BIG 7), `pde/` (BIG 8), `coupling/` (BIG 9 adapters over the
  Core `execution.multiphysics` runtime; participant state-completeness contracts), and
  `multiscale/` (BIG 10: macro windows, representative fast windows, aggregation with stated
  information loss, slow-state feed-forward, checkpoint/resume). `multiscale` orchestrates the
  others and owns no time, state, lifecycle, material or coupling authority of its own.
- `providers/` (BIG 11): provider-neutral external solver boundary (descriptive capability registry,
  content-derived execution identity, argv-only process boundary with stale-output refusal,
  provider records, declared cross-provider comparison). Provider adapters live in separate
  distributions under `providers/<name>/`; the provider map and license/deployment matrix are in
  [providers.md](providers.md).

## Claims organization

The first structural cleanup groups low-coupling implementations while preserving old import identity:

```text
claims/
  analysis/      sensitivity, robustness, challenge, impact
  governance/    decision context and evidence policy
  replay/        assessment bundle verification/replay
  adapters/      outer natural-language proposal boundary
```

Legacy flat paths such as `engcore.claims.sensitivity` remain shims. New internal code should prefer the grouped paths.

## Compatibility rule

A repository move must preserve scientific behavior and identity:

1. move implementation to the owning layer;
2. keep the previous import path as an identity-preserving shim;
3. add a dependency-direction/identity test;
4. remove a shim only through an explicit version or deprecation decision.

## Follow-up cleanup

The next structural slices should split `mcp/problem.py` by case/system boundary, reduce the remaining flat `claims/` modules, and move generic UQ algorithms out of claim orchestration only after their interfaces are proven domain-neutral.
