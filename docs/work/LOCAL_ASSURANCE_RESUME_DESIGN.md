# Local Assurance: future exact-source resume design

Status: design only. Resume is NOT implemented. --reuse still discards the
previous run and executes every gate. Failure diagnostics are local metadata,
never admissible gate records, receipts or certification evidence.

A safe resume must satisfy all of these conditions before skipping any gate:

- Exact source commit SHA and exact Git tree SHA match the recorded run.
  A descendant, equivalent checkout or cherry-pick cannot inherit its evidence.
- The checkout is clean before admission and execution, with byte-level tracked
  file checking and source HEAD checks. Each completed gate has its own bound
  clean-tree record; a run-level clean assertion cannot replace those records.
- Runtime identity matches: interpreter executable/version/content identity,
  installed distributions and their content identities, external provider
  identities, relevant environment, platform and execution configuration.
  Version labels or pip freeze alone are insufficient to prove byte identity.
- Each gate has an immutable manifest of its evidence paths, byte hashes and
  sizes; verify all hashes again before admission. Reject missing, duplicate,
  unexpected, partial, failed or unreadable records. Bind the gate name, exact
  selection/command, deterministic shard index/count and population digest.
- Bind an assurance-runner identity covering the runner, imported certification
  helpers, clean-tree checker, test/gate implementation, scope registry and
  mutation harness. A label is insufficient; record content digests under an
  explicit versioned protocol. Never mix evidence from runner implementations.
- Bind one run identity and source/tree/runner/runtime tuple to every artifact.
  Use an exclusive run lock and atomic completion records; concurrent writers
  cannot overwrite accepted evidence. An interrupted shard has no completion
  record and must rerun in a fresh isolated temporary copy.
- Revalidate all completion records and the aggregate assurance predicates before
  certificate generation. A failure diagnostic has no authority to mark a gate
  complete, skip a gate, issue SOURCE_PASS or authorize SAFE_TO_PUSH.

Any control-plane code change invalidates all previous evidence by default.
It changes the exact source/tree and potentially the meaning of admission,
execution, attribution or verification. A future exception would need an
explicit reviewed protocol and proof of equivalence; it is not supported now.
No cross-SHA or cross-runner reuse is allowed under this proposed design.

Recommendation: keep resume unimplemented until immutable gate completion,
runtime identity, exclusive ownership, runner identity and adversarial admission
tests exist as one reviewed protocol. Timing diagnostics help diagnose failures;
they do not establish these guarantees. Run full assurance from scratch only
when explicitly authorized after control-plane stabilization.
