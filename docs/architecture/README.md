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
                    |         \
                    v          +-> providers
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
- `providers/` is the external **solver** boundary: adapters for scientific solvers Forge executes and does not own (PyBaMM, PyBOP, SALib). Like `mcp` it is an outer consumer, not scientific authority — it imports the Core and the domains, nothing below it imports it, and its third-party dependencies are optional extras so that Core importability never depends on one. A provider that produces an answer produces the same `ScientificResult` a native solver does, which is what lets the credibility and claim path stay unaware that providers exist. See `docs/providers/README.md`.

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
