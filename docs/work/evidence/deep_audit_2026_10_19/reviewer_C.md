# Reviewer C — Multiphysics, Time, Coupling, Checkpoint/Rollback, State

Target: `D:/forge-main-337519d1`, HEAD `abed661f0d551f352e7a2c451d0df7fcc22bde5c` (verified with `git rev-parse HEAD`).
Read-only. No FORGE code executed. One stdlib-only derivation script:
`scratchpad/audit/c_reviewer_derivations.py`, run with `.venv/Scripts/python.exe -I -S` (output quoted under C-01 / C-02;
it is an independent derivation, not EXECUTED_REPRODUCED).

End-to-end paths traced line by line:

1. **System executor -> MultiphysicsAuthority -> MultiphysicsRuntime -> committed SystemState**:
   `system_runtime/executor.py:143-235` (run loop), `:242-416` (`_run_node`: inputs, identity, cache, outcome
   validation, applicability, state proposal, `state.advance`), `system_runtime/authorities.py:177-415`
   (`MultiphysicsAuthority.execute`: OD-27/B3a scenario checks, `runtime.run`, graph/plan fingerprint, conservation,
   `assess_run_outcome`, mocks/providers, outputs, `StateProposal(run.ended_at, ...)`), `execution/multiphysics/runtime.py:2180-2699`
   (`run`), `:1689-1821` (`_controlled_window`), `:1367-1588` (`_window`), `:998-1261` (`_iteration`), `:1271-1365`
   (conservation history), `:2769-2955` (`require_conservation`, `assess_run_outcome`), `system_runtime/state.py:190-226`.
2. **MultiscaleAuthority -> MultiTimescaleRuntime -> FastSystem (flagship cell-cooling)**: `authorities.py:461-777`,
   `multiscale/runtime.py:442-758` (`_execute`, `run`, `resume`, `_loop`, `_attempt`), `multiscale/fast.py`,
   `multiscale/windows.py:132-152`, `multiscale/aggregation.py:249-369`, `flagships/forge_flagships/battery_cooling.py:212-678`,
   `providers/pybamm/forge_pybamm/coupling.py:43-233`.
3. Electrothermal: native `systems/electrothermal/coupled.py:1970-2321` and adapter `runtime_adapter.py:153-484`
   (read for parity semantics; no new defect claimed there).

---

## C-01 — A coupled run's time window is never bound to the committed state's clock (state relabelled in time)

1. **ID**: C-01 · `new_or_known`: NEW
2. **Category**: Time / state advancement / evidence-context binding
3. **Exact file:line**:
   - `src/engcore/system_runtime/authorities.py:212-221` (identity pins `plan.fingerprint()`, so `plan.time.start/end` are fixed at construction), `:251-258` (`_initial_state` reads the owner values from `call.state` with no time), `:301-316` (`runtime.run(run_id, **kwargs)` — always over `plan.time`), `:391-407` (`StateProposal(run.ended_at, tuple(updates))`).
   - `src/engcore/system_runtime/authorities.py:727-732` (Multiscale fresh stage: `runtime.run(initial_slow_state=self._slow, ...)` starts at `timeline.horizon.start`, `multiscale/runtime.py:509`), `:664-686` (`_state_mismatch` compares VALUES only), `:755` (`StateProposal(record.reached.quantity, ...)`).
   - `src/engcore/system_runtime/executor.py:352-395` (the only time checks on a proposal: `> scenario.end + 1e-9` and, via `state.advance`, not backwards).
   - `src/engcore/system_runtime/state.py:204-205` (`if new time < self.seconds: refuse` — the only clock rule).
   - `src/engcore/system_runtime/records.py:171-187` (`StateProposal` has no start instant).
   - `src/engcore/system_runtime/preflight.py:150-154` (initial state time may be anywhere in `[scenario.start, scenario.end]`).
4. **Governing contract**: `state.py:3-6` "A SystemState is what the runtime commits ... digest-chained"; `state.py:142` "The complete authoritative state at one synchronization boundary"; `plan.py:266` "every commit advances the one state clock"; executor docstring `executor.py:13-15` "state advances only after the node succeeded ... on the SOLVED state". `StateView._CLOCK` (`state.py:262`) exposes `time` to committing nodes precisely so an authority could bind to it.
5. **Invariant violated**: CLAUDE.md "Evidence must remain bound to the exact context / decision it was produced for." A transition committed as `[t_state -> t_end]` was produced by physics over `[t_plan_start, t_end]`.
6. **Root cause**: the system-level transition record (`StateProposal`) carries only an end time; neither delegating authority compares the delegated run's start instant (`run.started_at` = `plan.time.start`; multiscale `record.start` = horizon start) with `call.state.time`, and the executor cannot, because the start instant is not in the proposal.
7. **Minimal triggering conditions**: any request whose committing MultiphysicsAuthority/MultiscaleAuthority node runs while the committed state clock differs from the delegated run's start. Examples: (a) two committing multiphysics nodes in sequence (planner requires them to be ordered, `plan.py:262-270`), each with a plan `[0, 10] s`; (b) an initial state declared at `t0 > scenario.start` (allowed by preflight) followed by a MultiscaleAuthority fresh stage; (c) a node whose plan starts later than the state clock (`[100, 200]` from state at `t=0`).
8. **Expected vs observed**: expected — refusal ("run starts at 0 s, committed state is at 10 s"), or a run integrated from the state's instant. Observed — `SUCCEEDED`, state committed at `run.ended_at`. Independent arithmetic (`c_reviewer_derivations.py`, integrator dx/dt = 1): case (a) commits `t=10 s, x=20` (exact `x(10)=10`), never refused; case (c) commits `t=200 s, x=100` (exact 200) — the interval `[0,100]` is silently treated as frozen.
9. **Reasoning**: `MultiphysicsAuthority` identity includes the plan fingerprint and `execute` refuses a run whose `plan_fingerprint` differs (`authorities.py:339-340`), so even a `runtime_factory` cannot move the run window to the state clock; the window is a construction constant. `state.advance` accepts any `t_new >= t_state`. Nothing else in the chain reads a start instant. Upstream guards checked: preflight (no time check per node), compile_plan (orders commits only), `_scenario_refusal_*` (scenario digest only), `require_conservation`/`assess_run_outcome` (internal to the run), `_state_mismatch` (values, rel 1e-12).
10. **Evidence class**: SOURCE_PROVEN (path traced end to end; no execution).
11. **Affected**: every `MultiphysicsAuthority` / `MultiscaleAuthority` node with `commits_state=True`; any downstream node/observable reading the committed owner; `SystemCheckpoint` resume (it re-verifies the chain but the chain itself is mislabelled). Flagship A's `aging` node is consistent today only because it is the sole committer and the initial state time is 0.
12. **False-support risk**: medium — an authoritative, digest-chained state at time T whose values are the result of a different time span; downstream constraint assessments and observables are presented as the state "at T". Not high because no current flagship triggers it.
13. **Replay/provenance**: the state chain records `produced_by` and digests, but no interval; a resumed or replayed run reproduces the same mislabelled chain (reproducibility, not correctness).
14. **Compatibility**: adding a start-time check refuses some currently-accepted requests; adding a `start` field to `StateProposal` changes its schema/digest (`records.py` PROPOSAL_SCHEMA).
15. **Certification**: `system_runtime/authorities.py`, `executor.py`, `state.py`, `records.py` all appear in `certification/current_core_v2.json` (grep count 1 each) -> OD-3.
16. **Genesis impact**: none directly (system runtime path, not the Mind/benchmark).
17. **Minimal reproduction plan (NOT executed)**: test with a one-participant `CallbackParticipant` integrator (`x += dt`) exposing `public_state`, plan `[0,10] s`, explicit; two `NodeSpec(MULTIPHYSICS_EXECUTION, commits_state=True, writes_owners=("p",), depends_on=...)`; `SystemExecutor(context).run(request)`; expect final `history[-1].time == 10 s` and owner `x == 20`. Cost < 1 s, in-process, no providers. Expected (current code): both nodes SUCCEEDED.
18. **Smallest correct repair (proposal)**: in `MultiphysicsAuthority.execute` refuse when `exact_seconds(run.started_at) != exact_seconds(call.state.time)` for a committing node (and for a non-committing node that reads state owners); in `MultiscaleAuthority.execute` refuse a fresh stage unless `call.state.time == timeline.horizon.start` and a resume unless it equals `checkpoint.at`. Longer term: `StateProposal` carries `start`, and `executor._run_node` requires `proposal.start == state.time`.
19. **Owner approval**: yes — OD-3 (certified files) and a schema decision if `StateProposal` gains a field.
20. **Self-challenge**: "authorities are trusted code and the request author must declare consistent plans." It does not survive: the system runtime exists to enforce context binding (it refuses an unordered commit, a scenario swap, a ghost provider); the plan/state time relation is checkable from data it already holds (`call.state.time`, `run.started_at`), and the planner's own text says each commit "advances the one state clock". A second argument — "the multiscale value check proves continuity" — fails: equal values at different instants are exactly the relabelling.

---

## C-02 — Per-window conservation reads SOURCE and RECEIVED from the same transfer; a lagged/Jacobi/explicit edge's actual consumption is never a term

1. **ID**: C-02 · NEW
2. **Category**: Physical consistency at interfaces / conservation gate
3. **Exact file:line**:
   - `src/engcore/execution/multiphysics/runtime.py:1310-1365` (`_balance`: `SOURCE -> transfer.source_value`, `RECEIVED -> transfer.value`, both from `transfers[edge_id]`),
   - `:2525` (`self._conservation_history(window, transfers)` with the window's FINAL-iteration transfers),
   - `:1032-1045, 1094-1156` (Jacobi: every participant advances on `frozen_edges` = iteration-start values; `current_transfers` are then replaced by this iteration's (relaxed) transfers),
   - `:1158-1200` (serial: a lagged target reads `current_edges` before its source runs),
   - `:947-978` (relaxation replaces `transfer.value` by the relaxed iterate),
   - `:2769-2820` (`require_conservation`), `system_runtime/authorities.py:346-349` (admission gate), `assembly/multiphysics.py:938-945, 233-240`.
4. **Governing contract**: `scientific/multiphysics/conservation.py:1` "Conservation declarations bound to executed multiphysics transfers"; `TransferMeasure.RECEIVED`; `require_conservation` docstring "Refuse a run as a scientifically successful coupled result unless every REQUIRED balance held in every window"; authority docstring (`authorities.py:185-187`) "required conservation held".
5. **Invariant violated**: CLAUDE.md "Verification does not become validation" / "Solver agreement does not prove physical truth" in its conservation form: a balance that is an identity of the transfer operator is recorded and gated as interface conservation.
6. **Root cause**: the balance terms are bound to `TransferResult` objects of the last iteration. For an edge whose target reads the value from the previous iteration (Jacobi; serial lagged edge) or the previous window (explicit coupling, every Jacobi edge and every serial lagged edge), the value the target actually advanced with is `edge_values[edge]` at iteration/window start, which is not a term of any balance. `RECEIVED` is the value the target will read NEXT, not the value it consumed.
7. **Minimal triggering conditions**: a graph with a declared `CoupledConservation` over an edge that is lagged in the plan (explicit coupling, or Jacobi, or a serial edge whose target precedes its source), and a time-varying source.
8. **Expected vs observed**: expected — the per-window residual reflects what left the source vs what entered the target during that window, or the record states that RECEIVED is the next-iterate value and that lag/staggering imbalance is not measured. Observed — residual `|source - received|` of one transfer: zero for a lossless edge whatever the lag. Independent arithmetic (explicit staggered, `q_n = n` W, dt = 1 s, 6 windows): recorded residual 0 J in every window; actual interface imbalance 1 J per window, 5 J cumulative (emitted 15 J, consumed 10 J). For an IMPLICIT converged run the hidden mismatch is bounded by the coupling criterion, not by the balance tolerance, so a balance tolerance of 1e-9 W can PASS while consumption differs by the coupling `atol`/`rtol*scale`. Secondary consequence (conservative direction): with CONSTANT/AITKEN relaxation, `RECEIVED` is the relaxed iterate, so a tight single-edge balance can FAIL on `(1-w)|H(x)-x|` although nothing was lost — a spurious refusal.
9. **Reasoning**: traced `run` -> `_controlled_window` -> `_window` -> `_iteration`: the dictionary handed back as `transfers` is `current_transfers`, populated from `_transfer_outgoing` of the final iteration; `_conservation_history` consumes exactly it. In explicit plans `_iteration` runs once with `frozen_edges`/`current_edges` = previous window's edge values.
10. **Evidence class**: SOURCE_PROVEN for the mechanism; CONTRACT_AMBIGUITY for what `RECEIVED` promises (no docstring defines it as "consumed").
11. **Affected**: any graph declaring `CoupledConservation` (assembly `AuthorizedMultiphysicsRun`, `MultiphysicsAuthority`); explicit and Jacobi plans most; the conservation history entries in `final_outputs["_conservation"]` and `_conservation_status`.
12. **False-support risk**: medium — `_conservation_status: pass` is read as interface closure to the declared tolerance; for explicit runs `COMPLETED_EXPLICIT` already notes "splitting error not quantified" (mitigation), for implicit runs nothing ties the conservation tolerance to the coupling tolerance.
13. **Replay/provenance**: deterministic; replay reproduces the same zero residuals.
14. **Compatibility**: adding a CONSUMED measure or a lag note changes conservation entry payloads (certified `conservation.py`, `runtime.py`).
15. **Certification**: `execution/multiphysics/runtime.py` and `scientific/multiphysics/conservation.py` are in `current_core_v2.json` (count 2 each) -> OD-3.
16. **Genesis impact**: none.
17. **Reproduction plan (NOT executed)**: reuse `tests/test_multiphysics_conservation_history.py` fixtures: two participants A (source, `q = t` W) and B (sink with output fed back so the A->B edge is lagged under explicit SERIAL order (B, A)), balance `SOURCE(e) == RECEIVED(e)` tol 1e-12 W, plan `[0,6] s` window 1 s; assert every entry `residual == 0` while the sink's consumed input sequence (logged in the callback) lags by one window. Cost < 1 s.
18. **Repair (proposal)**: record, per window, the value each target actually advanced with (`edge_values` at iteration/window start for lagged edges) as a distinct `CONSUMED` measure (or require balances on lagged edges to name it); at minimum label entries on lagged edges `measure_semantics: "next-iterate transfer, not consumption"` and refuse to report a conservation tolerance tighter than the coupling criterion on such edges as closure.
19. **Owner approval**: yes — scientific-design decision on conservation semantics + OD-3.
20. **Self-challenge**: "conservation of the transfer operator is all the runtime claims; staggering error is a splitting error owned by numerical_error." Partly survives for explicit runs (the splitting source is UNQUANTIFIED there). It does not survive for implicit runs, where the record presents a 1e-9 closure while the physics is only closed to the coupling tolerance, nor for the admission gate, which treats the identity as a physical precondition.

---

## C-03 — Parameter bindings change a coupled run but are in neither the run record nor its replay

1. **ID**: C-03 · NEW
2. **Category**: Identity / replay / incomplete record
3. **Exact file:line**: `execution/multiphysics/runtime.py:2191, 2315-2316` (`parameter_bindings` applied to participants), `:2259-2268` (`scenario_bound` excludes them), `:2677-2699` (record has no parameter field), `:311-357` and `:239-286` (`replay*` never passes them and cannot refuse — the record carries no trace); `execution/multiphysics/participant.py:287-323` (`apply_parameters` returns `()` when no values: a declared parameter left unbound is silently kept at the participant default); `assembly/multiphysics.py:891-924` (values come from `topology.parameter_values(topology_twins)`); `systems/topology.py:302-345`; `scientific/twins/definition.py:56-81, 218-219` (`TwinReference` = id + version, no content digest); `assembly/multiphysics.py:203-210` (`AuthorizedMultiphysicsRun` stores `graph_plan` with only `TwinReference`s).
4. **Contract**: runtime replay comment `runtime.py:249-261` (replay must refuse what it cannot reconstruct); `ParameterDefinition` "A participant parameter a topology ParameterBinding may bind to".
5. **Invariant**: "Evidence must remain bound to the exact context"; "Missing boundary conditions are never silently defaulted" (by analogy for a replayed run that silently reverts to defaults).
6. **Root cause**: parameters are a run input with no receipt and no digest; scenario-style binding was applied to inputs/conditions/state but not to parameters.
7. **Trigger**: a participant declaring `parameter_definitions` with a topology `ParameterBinding` (today only `tests/test_world_runtime_sprint1.py:155-179, 771`); two twins sharing `(twin_id, version)` with different parameter values, or `MultiphysicsRuntime.replay(record, ...)` of such a run.
8. **Expected vs observed**: expected — parameters recorded (or refused at replay); observed — identical record inputs for different parameter values; replay runs with participant defaults and returns a record that looks like a replay of the same run.
9. **Reasoning**: grep shows no other carrier of the values (`MultiphysicsRunRecord` fields at `report.py:546-568`; `GraphPlan` fields at `planning/records.py:502-521`).
10. **Evidence class**: SOURCE_PROVEN (omission); reachability LATENT (no production participant declares parameters).
11. **Affected**: assembly authorized runs with topology parameter bindings; replay APIs.
12. **False-support risk**: low today (latent), medium once a production participant declares parameters.
13. **Replay/provenance**: direct — replay is not of the same run and is not refused.
14. **Compatibility**: new record field / receipt -> serialization change.
15. **Certification**: `runtime.py`, `participant.py`, `assembly/multiphysics.py`, `report.py` are in `current_core_v2.json` -> OD-3.
16. **Genesis**: none.
17. **Reproduction plan (NOT executed)**: run the sprint-1 world fixture twice with twins `mass=1000 kg` and `mass=2000 kg` under the same `TwinReference`; compare `run.to_dict()` input sections (identical) vs `final_outputs` (different); then `MultiphysicsRuntime.replay(record, fresh participants)` -> no refusal. < 2 s.
18. **Repair**: `ParameterReceipt` records in the run record (value + source twin digest), include parameters in `scenario_bound`-style replay refusal, and a content digest in `TwinReference` or in the receipt.
19. **Owner approval**: yes (record schema, OD-3).
20. **Self-challenge**: "twin versions are immutable by convention" — nothing enforces it, and replay drops the values regardless of twin immutability.

---

## C-04 — Numerical-error accounting omits the window (zero-order-hold) coupling error of implicit transient runs

1. **ID**: C-04 · NEW (related to, not a variant of, OD-22/OD-32)
2. **Category**: Uncertainty/error ledger completeness
3. **Exact file:line**: `execution/multiphysics/numerical_error.py:336-342` (`_splitting_sources` returns `[]` for any non-EXPLICIT plan), `:257-333` (implicit plain converged windows -> ESTIMATED iteration sources only), `:166-182` (verdict ESTIMATED = "no source is open").
4. **Contract**: `execution/multiphysics/subcycling.py:8-12, 25-26` "every coupled input is HELD CONSTANT over the window ... The zero-order hold contributes a splitting error the runtime does not measure unless window error control is declared"; `scientific/multiphysics/plan.py:419-424` "Without it no time-discretization error is assessed"; `ErrorAccountingVerdict.ESTIMATED` docstring.
5. **Invariant**: "Missing uncertainty never becomes zero" (an omitted source reads as not open).
6. **Root cause**: the splitting/window error source is modelled only for explicit staggering.
7. **Trigger**: IMPLICIT plan, NONE relaxation, scalar (or identity-mapped) edges, transient participants, every window converged in >= 2 iterations with contraction ratio < 1.
8. **Expected vs observed**: expected verdict INCOMPLETE with an UNQUANTIFIED `run:window_time_discretization` source; observed verdict ESTIMATED.
9. **Reasoning**: direct reading; WindowErrorControl indicators (logged in `_window_control`) are not consulted either.
10. **Evidence class**: SOURCE_PROVEN (omission) / CONTRACT_AMBIGUITY (whether the source belongs to this ledger).
11. **Affected**: `assess_coupling_numerical_error` reports; `claims/coupling_numerical.py`.
12. **False-support risk**: low — the only consumer (`claims/coupling_numerical.py:164-177`) vetoes ESTIMATED as well, so no NUMERICAL channel passes; the defect is a mislabelled verdict/report.
13. **Replay**: none. 14. **Compatibility**: assessment payloads of implicit runs gain a source. 15. **Certification**: `numerical_error.py` not in `current_core_v2.json` (count 0). 16. **Genesis**: none.
17. **Reproduction (NOT executed)**: implicit Jacobi two-participant linear relaxation fixture (as in BR13 tests), call `assess_coupling_numerical_error(run).verdict` -> `ESTIMATED`. < 1 s.
18. **Repair**: add an UNQUANTIFIED window-discretization source for implicit runs with any transient participant (ESTIMATED-indicator when WindowErrorControl assessed every window, never a bound).
19. **Owner approval**: no certification; a small design decision on source naming.
20. **Self-challenge**: "time error belongs to the claim's refinement study." The module itself lists explicit splitting as coupling error; the implicit window hold is the same mechanism.

---

## C-05 — Flagship A can no longer execute its day-56 and multiscale nodes (PyBaMM origin-zero rule) — new consequence

1. **ID**: C-05 · NEW consequence of the R3 checkpoint-hardening decision (`docs/work/CHECKPOINT_HARDENING.md:38`), not on the brief's known list.
2. **Category**: Time origin / functional regression (fail-closed)
3. **File:line**: `providers/pybamm/forge_pybamm/coupling.py:146-158` (`initialize` requires `instant == 0`), `:161-166` (advance requires the held clock = request start); `flagships/forge_flagships/battery_cooling.py:579-582` (`day-aged`, `day-control` at `aged_start = 56 d`), `:244-274, 365-372` (fast system builds a runtime whose plan starts at each representative window start), `:413` (14-day macro windows).
4. **Contract**: flagship module docstring `battery_cooling.py:8-16`; R3 "Absolute origins other than zero are explicitly unsupported".
5. **Invariant**: none weakened (fails closed). 6. **Root cause**: the flagship drives the cell participant on the absolute scenario clock; R3 made non-zero origins a refusal; no flagship/doc update followed.
7. **Trigger**: any regeneration of Flagship A (`build_flagship`), `day_aged`, `day_control`, and the `aging` node's second macro step (resolved window at 14 d).
8. **Expected vs observed**: expected — the flagship regenerates; observed (static) — `ProviderRefusal("PyBaMM initial origin clock ...")`, `day_aged`/`day_control` FAILED, `aging` refused at macro step 1, `shift` BLOCKED, run PARTIAL. Committed bundles become non-reproducible.
10. **Evidence class**: SOURCE_PROVEN (static path); not executed (needs PyBaMM).
11. Affected: Flagship A only. 12. False-support risk: none (fail-closed). 13. Replay: committed Flagship A artifacts cannot be re-derived by execution. 14-15. Compat/cert: flagship not certified. 16. Genesis: none.
17. Repro (NOT executed): `python -m forge_flagships` Flagship A in the WSL battery env (~minutes); expect the refusal above.
18. Repair: shift the cell participant to a local clock (`instant - plan.start`) declared in its build, or keep origin zero and build each day's plan on `[0, DAY]` with the scenario offset carried in `current_at`/environment lookups.
19. Owner approval: yes (flagship regeneration decision). 20. Self-challenge: "documented limitation" — the limitation is documented; its consequence for the flagship is not.

---

## (a) Hypotheses not confirmed

- **H-1 Fixed-runtime reuse**: a `MultiphysicsAuthority` built with a fixed `runtime` (not a factory) re-runs the same participant objects on every `execute`; whether `participant.initialize` resets internal state is participant-defined and the runtime records but never checks the first `start_state_digest`. PyBaMM refuses (clock check) and the flagship uses factories, so no production path was found. `MultiphysicsAuthority.stateless = True` (`authorities.py:236-237`) is a declaration about the authority, not its participants.
- **H-2 Event from a non-accepted iterate**: `_window` attaches `aligned.event or outcome.event` (`runtime.py:1508`), so an EVENT_ALIGNED window can carry the event detected on an unconverged iterate of the longer window even if the converged re-run never re-triggered it. No consumer of `window.event` was found outside the runtime (grep), so no consequence established — OBSERVATION.
- **H-3 Concurrent failure ordering**: `concurrency.py:86-98` raises the first failure in plan order among concurrent participants; a retryable `CouplingWindowNotConverged` from an earlier participant can mask a hard refusal from a later one, so window control retries instead of refusing. Self-limiting (refusal reappears); low.
- **H-4 Relative coupling criterion scale**: `convergence.py:103, 154-198` scales relative residuals by the base-unit magnitude (kelvin for temperatures; datum-dependent for potentials/gauge pressures). Plans in-tree use `rtol = 0`; CONTRACT_AMBIGUITY only.

## (b) Inspected and found sound (with reasoning)

- **Rollback completeness**: `CouplingPlan.validate_against` (`plan.py:697-729`) requires every participant checkpointable with deterministic restore for IMPLICIT, any `window_control`, and event alignment; `_restore_all_unchecked` (`runtime.py:872-885`) re-checkpoints and compares digests; any restore failure retires the runtime and all participants (`:862-870`, `:819-833`). Implicit iterations restore at every iteration start (`:1013-1014`). No partial-restore path found.
- **Acceleration history vs rollback**: `RelaxationController` is rebuilt per run (`runtime.py:2206-2208`); Aitken state cleared per attempt (`relaxation.py:50-55`); IMVJ carries only accepted+converged, same duration/layout/supports (`acceleration.py:132-193`); step-doubling deep-copies and restores the accelerator (`runtime.py:1897, 1934`). IQN-ILS/IMVJ sign conventions re-derived: `x = H - W V^+ r`, `J = J_prev + (W - J_prev V)(DV)^+ D` — consistent.
- **Clocks**: boundaries are exact `Fraction`s; nominal grid `start + k*width` with drift/anchor bookkeeping (`runtime.py:2386-2452`); events and STEP change instants are forced boundaries; subdivided ends tracked exactly (`_accepted_end_exact`); window records validated for contiguity and step spans (`report.py:681-737`); `assess_run_outcome` re-checks contiguity in exact seconds.
- **Residual on the unrelaxed transfer**: `runtime.py:1205-1228` compares `edge_values` (iteration start) with `unrelaxed`; serial lagged/forward requirements derived (`plan.py:631-671`) and re-guarded at labelling (`runtime.py:1545-1553`).
- **Executor reuse cache**: identity includes `state.digest`, which includes `request_digest`/`environment_digest` (`state.py:229-231`), so no cross-request reuse; only deterministic+stateless authorities, only SUCCEEDED outcomes.
- **System checkpoint resume**: `verify_checkpoint` (`system_runtime/checkpoint.py:25-122`) re-derives the full state chain from the request's initial state, prefix property, receipts vs history, authority payload digests.
- **Multiscale reuse/representativity**: fast cache key is the full request identity including the exact window (`fast.py:150-178`), so no cross-window reuse; repetition is whole periods only (`windows.py:132-152`); periodicity measured at the union of change points; CYCLE_COUNT closure logic correct; affine INTEGRAL_DOSE refused.
- **Fan-in / units**: SUM over affine units refused (`graph.py:450-457`); scalar transfers convert with `.to(target unit)`; spreads use base units for affine scales.
- **Scenario binding (OD-27/B3a)** before and after `run_kwargs`, and on every receipt of the returned record (`authorities.py:119-174, 297-345`).

No change was made to the repository. All verdicts above are static; nothing was executed except the stdlib derivation script.
