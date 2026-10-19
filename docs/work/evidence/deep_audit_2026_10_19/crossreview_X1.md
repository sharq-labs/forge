# Cross-review X1: an adversarial check of A-01, A-03, A-05, C-01, C-02 and C-03

Target: `D:/forge-main-337519d1`, HEAD `abed661f` (I confirmed it with `git rev-parse`). This was read-only. I used
Read/Grep, `sed` and `git rev-parse`, and I ran no FORGE code. I wrote one stdlib script,
`scratchpad/audit/x1_derivations.py`, and ran it with `-I -S`. Its output is an independent derivation, not
EXECUTED_REPRODUCED.

I traced every path myself. I did not reuse line numbers from the original reports. All the files involved are
listed in `certification/current_core_v2.json`, so every repair below needs OD-3.

I checked whether any of these is already known. I grepped `docs/work/*.md` (REMEDIATION, POST_MERGE, ACTIVE_PLAN,
PROGRESS and the others) for: `_scalar_outputs`, `compare_runs`, `condition_repairs`, `report_run_id`,
`criteria_authority`+replay, `StateProposal`, `state clock`, `started_at`, `parameter_bindings`, `ParameterReceipt`
and `TransferMeasure`. None of the six is a known item. The only nearby entry is PROGRESS.md:5209 (BR11). It accepted
the `_` skip for `_concurrency` and `_window_control` only.

---

## A-03 — CONFIRMED (stays MAJOR). The trigger the reviewer gave is mostly refuted; a stronger trigger replaces it.

**What I traced:**
- `assembly/replay.py:531-546`. `_scalar_outputs` drops:
  - every `_` key;
  - every non-Mapping value, and every Mapping without a numeric `magnitude` (so FieldRecords are dropped);
  - `units`.

  Its docstring says those are "still covered by the identity comparisons below". That is false. `:557-571` compares
  only the graph and plan fingerprints, the scenario digest, the window count and `ended_at`.
- `compare_runs` (`:549-638`) never reads:
  - `external_inputs`, which is where the input uncertainty lives;
  - `_uncertainty`, `_edge_uncertainty` or `_coupling_error`;
  - `replayed.system_validation`, `system_uncertainty` or `system_verification`. These are recomputed at
    `assembly/multiphysics.py:944-1044` and then discarded.
- `ReplayEvidence` (`:233-238`) only requires `replayed_run_digest != original`. `certifies()` (`:456-495`) checks
  identity, the seal and the comparison digest only.
- The certification gates read the stored record: `assembly/certification.py:456-526`, `_uq_coverage:387-397`.

**Strongest counter-argument, and it partly succeeds.**
- The reviewer's "typical cause" was a code change in a UQ, validation or verification implementation. That change is
  refused upstream:
  - `CompositionPack.authority_digest` (`compositionpacks/registry.py:87-122`) includes the
    validation, uncertainty and verification `ArtifactImplementationFingerprint`s.
  - `implementation_fingerprint` (`domainpacks/frozen.py:39-89`) hashes the callable's source, its **whole module
    file bytes** and its bytecode.
  - Participant factories are fingerprinted the same way (`executionpacks/registry.py:71`).
  - `execute_authorized_graph_plan` refuses a moved digest (`multiphysics.py:785-806`), so replay returns
    REFUSED_UNREPRODUCIBLE.
- So the reviewer's trigger only survives for a change in a transitively imported helper module, or in a library or
  environment.

**Stronger trigger, needing no code change (SOURCE_PROVEN):**
1. `replay_authorized_graph_plan` takes `external_uncertainty` from the caller, defaulting to `None`
   (`replay.py:651,673`). It is not bound to the original.
2. `_external_by_participant` (`execution/multiphysics/runtime.py`) turns a missing entry into `Uncertainty.unknown`.
3. The input values come from `graph_plan`, so they are unchanged and the scalars match.
4. Only `run.external_inputs[*].uncertainty`, `_uncertainty` and `system_uncertainty` differ, and `compare_runs`
   reads none of them.
5. Result: REPLAYED_MATCH, a valid seal, and COMPUTATIONAL_REPLAY_VERIFIED. Meanwhile
   `UNCERTAINTY_AUTHORITY_SATISFIED` and `UQ_CHANNEL_COMPLETENESS` pass on the original's stored quantified UQ, which
   the replay never reproduced.

This replay evidence was produced under a different input-uncertainty context and still certifies. That violates
"Evidence must remain bound to the exact context".

**Other points:**
- Units: `validate_port_coupling_value` (`scientific/multiphysics/value.py`) checks only dimensionality, so a
  K-to-degC relabel with the same magnitude would be accepted by both the port check and `compare_runs`. That trigger
  is narrow.
- Is UQ just a function of the scalars, so that comparing it is redundant? No. The UQ comes from separate producer and
  participant code, and from caller-supplied input UQ.

**Repair:** in addition to A-03's list, compare `external_inputs` (value and uncertainty), and bind or forbid a
caller-supplied `external_uncertainty` / `topology_twins` that differs from the original.

## A-05 — CONFIRMED, MINOR

**What I traced:**
- `claims/assessment.py:873-899`. `verify_assessment` checks only `view.outcome` and `view.binding_problems`.
- `_build_record` copies the view verbatim (`:518`), so the full-record compare at `:931` is tautological for the
  execution view.
- `_execution_view` (`:748-759`) shows that `run_id`, `plan_digest`, `capability_id`, `instance` and `report_run_id`
  are pure functions of the plan and the report.
- `condition_repairs` becomes `domain_repair:`-sourced actions (`:297-309`).

**Counter-argument:** the bundle digest is an unkeyed `tagged_digest` (`replay/bundle.py:219,287`). The module
docstring (`:21-35`) explicitly says a consistent rewrite passes offline and that offline standing is never
publishable.

**Why the finding survives:** this edit is not a consistent rewrite. The record contradicts its own plan, and that is
cheap to detect without a key, while the docstring claims it re-derives "every part". Standing impact is nil:
`replay_bundle` still refuses VERIFIED through `_compare_replay_nodes` and `_has_bound_replay_result`.

## A-01 — CONFIRMED, MINOR (fails closed)

**What I traced:**
- `replay/bundle.py:742-749` calls `assess_claim` with no `criteria_authority`.
- `assessment.py:616` then writes `CALLER_AUTHORED_CRITERIA`.
- `_compare_replay_nodes` (`:556-564`) reports the missing and extra keys and the changed authority, so the result is
  NOT_REPRODUCIBLE.
- `make_bundle` (`:202-219`) does not refuse grounded records, and `product/runtime.py:325` produces them.
- No src consumer calls `replay_bundle` (I grepped product and mcp).

**Counter-argument:** replay judges deliberately under the caller's criteria. That fails: the block is
re-verified offline (`:928`) and also inside `assess_claim` (`:792-794`), so passing it through cannot raise support.

## C-01 — CONFIRMED, MAJOR (latent: no production trigger)

**What I traced:**
- `system_runtime/authorities.py:206-214`: the identity pins `plan.fingerprint()`.
- `:339-340`: a run under a different plan is refused, so not even a factory can move the window.
- `runtime.run` (`execution/multiphysics/runtime.py:2180-2197`) has no start argument and always starts at
  `plan.time.start` (`:2293-2328`).
- `:391-407` commits `StateProposal(run.ended_at, ...)`.
- `executor.py:356-395` checks only "beyond scenario end".
- `state.py:204-205` refuses only backwards time.
- Preflight (`preflight.py:144-154`) only bounds the initial time inside the scenario.
- `plan.py:262-270` orders committers and allows two committers on the same owner.
- No authority reads `call.state.time`. Grepping `state.time` under `system_runtime/` finds only the executor and
  preflight lines.
- Multiscale: `_state_mismatch` (`authorities.py:664-686`) compares values only, and a fresh stage runs from the
  horizon start.

**Counter-argument:** the request author must declare consistent plans. That fails, because the planner refuses
analogous mis-declarations itself (unordered commits). Reusing one authority for consecutive stages is a natural
trigger.

**Independent derivation:** two commits of a plan over [0,10] s with dx/dt=1 end at t=10 with x=20, while the true
x(10) is 10. Both commits are accepted.

**Production reach:** the only production committer is `battery_cooling.py:639`, so the defect is latent.

## C-02 — CONFIRMED_REDUCED_SEVERITY: MINOR, reclassified CONTRACT_AMBIGUITY

The mechanism is SOURCE_PROVEN:
- `_balance` (`runtime.py:1310-1365`) reads `source_value` and `value` from the same final-iteration
  `TransferResult`.
- Relaxation replaces `value` and keeps the raw `source_value` (`:947-978`).

**Counter-arguments, which mostly succeed:**
- The contract defines the balance over transfers:
  - `conservation.py:1` says "bound to executed multiphysics transfers";
  - `CoupledConservation`'s docstring says "a domain-neutral balance whose terms are realized transfers".
- The repo separates the two notions:
  - `interface_exchange.py:172` labels these residuals with `coupled_physical_conservation: "unknown"`;
  - DEFERRED_VALIDATION.md:540 says "transfer conservation residuals as DIAGNOSTICS".
- The explicit-coupling lag is disclosed:
  - `numerical_error._splitting_sources` marks it UNQUANTIFIED for EXPLICIT plans;
  - the authority note says "splitting error not quantified".
- For implicit runs, the gap between consumed and received is bounded by the recorded coupling criterion.
- No production graph declares a `CoupledConservation`. The only `ConservationTermBinding(` is in
  `providers/fenicsx/tests`.
- The production electrothermal pack checks consumption separately (`power_transfer_conservation`, "thermal
  heat_input consumed in same serial window", `builtin_electrothermal_feedback.py:752-761`).

**What survives:**
- The `require_conservation` and authority docstrings call this "required conservation held" without the "transfer"
  qualifier.
- A relaxed single-edge balance can fail spuriously, which fails closed. The derived residual is 5e-7 for
  w=0.5 and |H-x|=1e-6.

## C-03 — CONFIRMED, MINOR (latent)

**What I traced:**
- `runtime.py:2315-2316` applies the bindings.
- `_bind_parameters` (`:2054-2068`) discards the acknowledged `ParameterValue`s that `apply_parameters` returns
  (`participant.py:287-323`).
- `MultiphysicsRunRecord` has no parameter field.
- `scenario_bound` (`:2259-2266`) excludes parameters.
- `replay` and `replay_with_factory_registry` (`:239-357`) never pass parameters and cannot refuse.
- `TwinReference` is id plus version, with no content digest (`twins/definition.py:56-81`).
- The `topology.parameter_values` check is `twin.reference != instance.twin` only (`systems/topology.py:322-327`).

**Mitigations:** assembly replay re-reads the twins and compares the scalars, so a parameter that moves the outputs
fails closed there. There are no production `parameter_definitions=` (grep).
