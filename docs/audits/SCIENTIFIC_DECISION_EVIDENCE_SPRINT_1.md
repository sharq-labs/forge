# Decision-Evidence Bridge Follow-up — Honest Unknown Discrepancy

PR #50 is stacked on the current PR #49 decision-readiness branch.

The original bridge work is now owned by PR #49.  This follow-up keeps only
one non-duplicative hardening from the earlier #50 implementation:

- model-form discrepancy may be explicitly `UNKNOWN`;
- an omitted bridge discrepancy becomes `UNKNOWN`, never `ZERO_DECLARED`;
- the assurance discrepancy check treats `UNKNOWN` as INCONCLUSIVE and
  assurance-blocking;
- explicit `ZERO_DECLARED` and `CONSTRAINED_PRIOR` semantics remain unchanged.

This reconciliation deliberately does **not** reintroduce the old #50 Arbiter
change that allowed any registered critic to satisfy `validation_level:*`.
PR #49's explicit `validation_level_issuer` authority gate remains in force.

It also does not keep a second `engcore.integration` bridge beside
`engcore.mcp.sria_bridge`; one production bridge is enough.
