# Authority Integrity Map (Big Rocks campaign: Authority Integrity → Real Escrow → Battery Blind Readiness)

Source-level inventory on branch `feat/big-rocks-authority-escrow-battery` (base `origin/main` `4634eba2`). It is a
statement of what the code does, with file:line references to the base tree. Each row names the one canonical owner.
The **Target** line says what this campaign changes. Nothing listed as CORE_CERTIFIED (`tools/certification/core_certificate.py`)
is edited: `scientific/**`, `credibility/evidence_graph/**`, `sria/admission.py`, `sria/assurance/*.py`,
`sria/evidence.py` and `sria/gateway.py` are consumed read-only.

## Cross-cutting facts (base tree)

- **No asymmetric signatures anywhere.** There is no ed25519, signing key, public verification material, key rotation,
  revocation or key epoch in `src/`. The `cryptography` distribution is present in the environment (it arrives with
  `[mcp]` through `pyjwt[crypto]`), but no module imports it.
- **Every HMAC key is per process and never persisted:**
  - `sria/admission.py:386,411-417` (`secrets.token_hex(32)`);
  - `claims/falsification.py:231` (`os.urandom(32)`; owner tokens `:437`);
  - `claims/multiplicity.py:35` (module-global `_SEAL_KEY`);
  - `blindfold/escrow.py:97-98,167` (master seed and capability tokens).
- **Every hash chain is unkeyed sha256 or HMAC-in-memory.** The chains: FalsifierRegistry, NoveltyLedger,
  CampaignEventLog (`sria/campaign/events.py:14-21`, which states it is not tamper evidence), the escrow log (unkeyed
  outer chain), SystemState and DesignHistory.
- **The only file-persisted, anchored chains** are the SRIA campaign checkpoint store
  (`sria/campaign/persistence.py:1792-1826`) and the design memory (`claims/design_memory.py:91-112`, anchored by
  `sria/campaign/anchors.py`). No authority record or discovery ledger is written to disk.

## Records

### NodeReceipt (`system_runtime/records.py:390-462`, issued by `SystemExecutor._receipt`, `executor.py:445-454`)
- SUBJECT_IDENTITY: one plan node attempt: `node_id`, `plan_digest`, `request_digest`, `node_digest`,
  `execution_identity_digest` (`executor.py:276`).
- ISSUER_IDENTITY: none. `authority_identity_digest` is self-declared by the authority object; `AuthorityRegistry.resolve`
  compares it with the plan's pin by equality (`records.py:361-369`). The executor is not identified.
- RESULT_BINDING: `output_digests` = sorted `(name, OutputValue.digest)` (`executor.py:453`) plus an output stamp, state
  digests and provider record refs.
- PERSISTENCE: `to_dict`/`from_dict` only, embedded in `SystemCheckpoint` / `SystemRunResult`. Never written to disk.
- VERIFICATION_PATH: `_verify_stored` (`executor.py:434-443`), `verify_checkpoint` (`checkpoint.py:25-122`) and
  `compare_runs` (`replay.py:61-110`). All are unkeyed self-consistency checks.
- CURRENT_TRUST_ASSUMPTION: the bytes came from the real executor. Anyone holding the dict can recompute every digest.
- KNOWN_RESIDUAL: forgery is not mentioned anywhere. **Target (Rock 1):** an EXECUTOR-role issuer attests the receipt
  (`receipt.digest` plus its output digests) into the persistent authority ledger. Evidence then names that attestation,
  and its subject digest must be one of the attested output digests.

### ValidationCheck (`scientific/results/validation.py:641-911`; CORE_CERTIFIED)
- SUBJECT_IDENTITY: `name` and `establishes`. There is no result field.
- ISSUER_IDENTITY: written as evidence lines and re-verified against source-pinned registries (`_issuer_gap`, `:225-276`).
  - Oracles: `scientific/oracles.py:97-118`.
  - Consensus routes: `domains/__init__.py:264`.
  - Analytic references and thresholds: `domains/__init__.py:134,196`.
  - NUMERICALLY_CONVERGED and DIMENSIONALLY_VALID have no issuer check.
- RESULT_BINDING: none verified. Stated at `:249-252` and `:342-345`.
- PERSISTENCE: `to_dict`/`from_dict` only.
- VERIFICATION_PATH: the constructor's VAL-01 check on every read; `ValidationReport._require_every_strong_level_issued`.
- CURRENT_TRUST_ASSUMPTION: registry strings are public, so a copy of the exact lines passes.
- KNOWN_RESIDUAL: the copy/rebind gap. **Target:** the check is admitted for credibility only when the authority ledger
  holds an attestation of `record_digest(check)`. The attestation must come from a NUMERICAL_VERIFICATION issuer
  (verification levels and independent routes) or a VALIDATION issuer (benchmark/experimental validation), and must be
  bound to the subject result and the decision context. The VAL-01 re-verification stays.

### ApplicabilityReport (`system_runtime/records.py:141-167`)
- SUBJECT_IDENTITY: `check_id`; the subject is implicit in `evidence_digest`.
- ISSUER_IDENTITY: none. It is created by authority callbacks (flagships), never by `src/engcore`.
- RESULT_BINDING: `evidence_digest` only. `credibility_vector` requires it to equal the subject node's content digest.
- PERSISTENCE: inside the NodeReceipt dict.
- VERIFICATION_PATH: shape only (`from_dict`).
- CURRENT_TRUST_ASSUMPTION: the caller supplies a genuine report.
- KNOWN_RESIDUAL: an omitted negative report cannot be seen. **Target:**
  - It is admitted only when attested by an APPLICABILITY issuer for the subject and context.
  - Every attested 'outside' / 'unknown' report about the subject is read FROM THE LEDGER, so omitting it from the call
    changes nothing.

### ChannelEntry / UncertaintyBudget (`sria/assurance/uncertainty_budget.py:93-434`; CORE_CERTIFIED)
- SUBJECT_IDENTITY: channel plus free-text `source`; the budget is identified by `value_name` only.
- ISSUER_IDENTITY: none.
- RESULT_BINDING: none.
- PERSISTENCE: `to_dict`/`from_dict`.
- VERIFICATION_PATH: `__post_init__` shape rules.
- CURRENT_TRUST_ASSUMPTION: a caller-supplied record plus a source pin on the carrying node.
- KNOWN_RESIDUAL: unbound. **Target:** admitted only when attested for the subject and context. The issuer role depends
  on the channel:
  - aleatoric (measurement) → MEASUREMENT;
  - numerical → NUMERICAL_VERIFICATION (the consumer also accepts UNCERTAINTY for numerical UQ, see `FACTOR_ROLES`);
  - other channels → UNCERTAINTY.

### EvidenceGraph / EvidenceNode / EvidenceProvenance (`credibility/evidence_graph/*`; CORE_CERTIFIED) and TrustedSourceRegistry (`scientific/knowledge/trust.py:50-77`)
- SUBJECT_IDENTITY: `evidence_id` plus `content_digest`. The provenance `claim_digest` equals the content digest.
- ISSUER_IDENTITY: `EvidenceProvenance.issuer` with self-carried pin fields. The real trust check is the caller-supplied
  `TrustedSourceRegistry` (`credibility_vector._GraphView.trusted_provenance`).
- RESULT_BINDING: `content_digest` = digest of the record the node carries.
- PERSISTENCE: `to_dict`/`from_dict` (two schemas for one class: `graph.py:49-62` and `serialization.py:13-24`).
- VERIFICATION_PATH: structural checks; trust is decided at assessment time.
- CURRENT_TRUST_ASSUMPTION: the caller supplies the right registry and a complete graph.
- KNOWN_RESIDUAL: deleted nodes or edges change the bound fingerprint, but the module cannot know they are missing.
  **Target:** unchanged (certified). Issuer-bound admission sits beside it, in the consumer.

### TrustEnvelope (`claims/redteam.py:343-385`)
- SUBJECT_IDENTITY: `claim_id`, `subject_digest` (the claim statement), plus the space and plan digests.
- ISSUER_IDENTITY: none. It can be built by hand: there is no `__post_init__` and no `from_dict`.
- RESULT_BINDING: the statement, not a computed result.
- PERSISTENCE: `to_dict` only.
- VERIFICATION_PATH: `credibility_vector._coherent` plus an isinstance check.
- CURRENT_TRUST_ASSUMPTION: it came from `run_red_team`.
- KNOWN_RESIDUAL: route families are self-declared. **Target:**
  - ADVERSARIAL counts only when a RED_TEAM issuer attests the envelope for the subject and context.
  - Attested FALSIFIED / UNKNOWN envelopes about the subject are read from the ledger.

### ScientificBelief / BeliefUpdateGateway (`sria/gateway.py:154-476`; CORE_CERTIFIED) and admission (`sria/admission.py:626-740`)
- SUBJECT_IDENTITY: `evidence_id`, `record_hash`.
- ISSUER_IDENTITY: `arbiter_id`, verified by a per-process HMAC declaration signature; authorizations are single-use.
- RESULT_BINDING: `record_hash` over the evidence fields.
- PERSISTENCE: in memory only.
- VERIFICATION_PATH: `verify_admission`.
- CURRENT_TRUST_ASSUMPTION: same process (`admission.py:45-47` states that durable admission records are deferred).
- KNOWN_RESIDUAL: per-process secrets. **Target:** unchanged (certified). Recorded as
  TRUST_REPAIR_DEPENDENCY_CANDIDATE: durable signed admission belongs to the certified lane.

### Twin evidence bridge (`claims/twin_evidence.py:145-197`; `systems/twin_revision.py:164-373`)
- SUBJECT_IDENTITY: `sria:<evidence_id>@<record_hash>` pointers; the twin `revision_id` is a content digest.
- ISSUER_IDENTITY: none of its own. It resolves against caller-supplied SRIA records and the gateway belief.
- RESULT_BINDING: record hash and context.
- PERSISTENCE: twin `serialize`/`from_dict`.
- VERIFICATION_PATH: pointer resolution, labelled "pointer_resolution_not_a_validation_verdict".
- CURRENT_TRUST_ASSUMPTION: same process.
- KNOWN_RESIDUAL: inherits the gateway's per-process trust. **Target:** unchanged; it inherits Rock 1 only via credibility.

### Discovery registries (`claims/falsification.py`, `claims/multiplicity.py`, `claims/novelty.py`, `sria/decision/hypotheses.py`)
- SUBJECT_IDENTITY: hypothesis id plus content and claim digests; falsifier digest; campaign id; acquisition ids.
- ISSUER_IDENTITY: the ExposureAuthority key fingerprint (`falsification.py:260-263`); owner tickets (`os.urandom`); the
  multiplicity seal (module-global HMAC key).
- RESULT_BINDING: falsifiers bind `hypothesis_content_digest`; releases carry an HMAC over content and sequence.
- PERSISTENCE: none. Every chain lives in memory; `verify` needs the live object.
- VERIFICATION_PATH: `verify_chain`, `verify_status(anchor=)`, `verify_promoted`, `verify_novelty`. All require the issuing
  process.
- CURRENT_TRUST_ASSUMPTION: one Python process for the whole campaign.
- KNOWN_RESIDUAL: `falsification.py:41-43` ("no persistence or attestation") and `multiplicity.py:14-15`. **Target:** a
  durable campaign (`claims.durable_campaign`). Every state-changing operation is journaled as an EXPOSURE-role
  attestation in the authority ledger, with the resulting chain heads. On restart the journal is replayed through the
  same code paths and every head is re-checked. Keys and owner tickets are derived from externally supplied key
  material, never from process randomness.

### Blindfold escrow (`blindfold/escrow.py:93-452`, `escrow_server.py`)
- SUBJECT_IDENTITY: campaign id, universe id (`bf-` + sha256(seed, kind)[:16]) and query id.
- ISSUER_IDENTITY: none. The bearer capability tokens are per process; responses are unsigned.
- RESULT_BINDING: the log binds HMAC-keyed query/response digests; the outer chain is unkeyed.
- PERSISTENCE: none. Budgets, submissions and the log are lost when the process ends.
- VERIFICATION_PATH: `verify_log` (unkeyed chain).
- CURRENT_TRUST_ASSUMPTION: same OS user. In-process and subprocess transports are both labelled
  SECURITY_BOUNDARY_NOT_PROVEN.
- KNOWN_RESIDUAL: `escrow.py:21-40`. **Target (Rock 2):**
  - Escrow-owned private storage (0700): master seed, an ed25519 escrow identity, and a keyed append-only journal of
    every accepted request.
  - Budgets and submissions are rebuilt by replay after restart.
  - Requests are MAC-bound to a capability.
  - Responses are signed by the escrow identity and bound to the request digest.
  - An isolated deployment profile runs Discovery under a separate uid in private namespaces.

  **Delivered (protocol v4, after checkpoint B):**
  - **Authentication before state.** An unauthenticated request gets one uniform refusal with no sequence or head.
    It is counted service-wide (`auth_failures`) and never enters a campaign chain.
  - **Single-use query ids**, keyed `op:universe:qid` (no `:` in ids). Log reads are durable too.
  - **Rollback and replacement.** Requests carry `last_sequence` and `last_head`. Clients keep a durable
    `EscrowCheckpoint` (operator and evaluator in the demo). A truncated journal, a restored backup or a replaced
    history is an `EscrowIntegrityError` for any client holding a later checkpoint.
    - Residual: a client without a checkpoint cannot detect it, and neither can the escrow alone.
  - **Refuses to start** on a missing journal (deleted), a torn line, or a broken keyed chain.
  - **Universes bound at creation.** A keyed digest of every hidden world and of the generator is journaled at
    creation; a universe that no longer re-derives refuses to start.
  - **Observation noise** in a stored escrow is seeded by the log position and the request digest.
  - **Clients always pin** the escrow key; an integrity failure is never an `EscrowRefused`.
  - **Labels.** The escrow always states `SECURITY_BOUNDARY_NOT_PROVEN`; no flag can raise it. A verified level is
    the isolation demo's record, bound to the escrow key id and to mechanism and check digests.
  - **Demo checks.** The launcher verifies each Discovery process from outside (/proc: ids, capabilities,
    no_new_privs, namespaces, the tmpfs over the storage). A journal canary is searched as a substring in every file
    changed since creation, with a positive control (`leak_control=True` → NOT_PROVEN).

### Other registries
- Risk policies: `claims/credibility_vector.py:757-790`, process-global, stricter-only.
- Domain, oracle, route and threshold pins: source constants, certified.
- Bundle manifests (`mcp/bundle.py`, `engineering/bundle.py`): unkeyed. Out of scope.

## The new authority layer (`engcore.authority`, non-core)

- **Owner and dependency.** The layer is owned by `engcore.authority`, imported by `claims` and `blindfold`, and it
  imports nothing above `engcore.authority`. It depends on the optional `[authority]` extra (`cryptography`, ed25519); an
  absent extra REFUSES. It does not create a second evidence model: it signs and orders DIGESTS of the existing records,
  with each record carried whole and deep-frozen.
- **AuthorityLedger.** One append-only, hash-chained ledger of signed events: GENESIS, REGISTER, SET_ROLES, ROTATE,
  REVOKE and ATTEST.
  - Administrative events are signed by the root key fixed at genesis.
  - A key is registered or rotated in only with a PROOF OF POSSESSION: the key signs (ledger, issuer id, its own key
    class).
  - ATTEST is signed by the issuer's key. It is admitted only if, at that sequence, the issuer exists, is not revoked,
    holds the role, and the signing key is the issuer's active key.
  - Persistence is a JSONL file, appended under an exclusive lock and only if the file still holds exactly the events
    the writer verified (no fork). A ledger object whose write may have landed is poisoned.
  - On load every signature (canonical lower-case hex), link and state transition is re-verified, and the ledger must
    extend the consumer's pinned `TrustAnchor`: ledger id, root key, profile, and a (sequence, head) it already saw.
- **Profiles and key classes.** A ledger is created `test` or `production`. A production ledger refuses test-class keys
  and a test root, at registration and again on load.
  - A `Signer` is minted only by a key provider: `EphemeralKeyProvider` mints `test`, `DirectoryKeyProvider` mints
    `production`. A minted `Signer` is immutable and is not a dataclass, so `dataclasses.replace`, attribute assignment
    and pickling cannot relabel it.
  - **What a key class means is limited.** It is the key holder's ASSERTION about custody: any holder can sign a
    possession proof for either class with its raw `sign`. It is checked against the ledger profile and grants no
    authority.
  - Inside one process this is construction, not isolation: the minting token is reachable by introspection.
- **Consumer pinning.** `assess_credibility(authority=, trust_anchor=)` refuses:
  - an object that is not exactly `AuthorityLedger` (a subclass could override what is verified);
  - a ledger that was not `open()`ed against an anchor;
  - another ledger id, root or profile;
  - a ledger that does not extend the anchor passed in the call.

  A production ledger makes a report `issuer_bound`; so does a test ledger with `allow_test_profile=True`, which the
  report states (`test_mode`) and binds into `inputs_digest`. **`requirement_met` is never true in test mode**: a
  test-mode report exposes `requirement_met_in_test_mode` instead, for tests and dry runs.
- **What `issuer_bound=True` establishes, and what it does not.**
  - It establishes that every backing record was signed in a ledger re-verified on open, by an issuer that the
    ledger's root authorized for the factor's role, and that the ledger extends the TrustAnchor passed in this call.
  - It does NOT establish that the anchor belongs to the consumer. The call cannot tell operator-configured trust from
    a root the caller minted: `generate_key_files` + `create` + `open` is enough (pinned by
    `test_residual_the_anchor_is_the_trust_root_so_it_never_comes_from_the_call_path`).
  - Authority therefore rests entirely on who chose the anchor's `root_key_id`. That must be operator configuration
    outside the call path, never planner, LLM or MCP input. A guard test checks that `engcore.mcp` never carries
    `authority`, `trust_anchor` or `allow_test_profile`.
  - In-process Python can also forge a report or reach the minting token. This layer protects against tampered
    persisted records and unauthorized issuers, not against code running in the consumer's process.
- **Key material.**
  - `DirectoryKeyProvider` reads 0600 regular files (no symlinks) owned by the process user, from a 0700 directory outside
    any git checkout.
  - `generate_key_files` checks placement BEFORE creating anything.
  - Private key material is never committed.
- **Attestation.** An attestation binds:
  - the record kind and schema;
  - `record_digest`, frozen at construction, plus the record itself;
  - `subject_digest` and `subject_output`;
  - `receipt_digest` (the EXECUTOR attestation of the NodeReceipt that produced the subject);
  - `context_digest`, the role and the issuer.
- **Evidence verification refuses:**
  - an unknown or revoked issuer, a wrong role, a retired or substituted key, or a bad signature;
  - a wrong result digest or a receipt that does not contain it;
  - a receipt not attested by an EXECUTOR issuer, or attested after the evidence;
  - a wrong context;
  - **self-issuance**: an evidence issuer that attested, as executor, this receipt or any other receipt producing the
    same output digest;
  - a record (or its receipt) signed inside a root-declared **compromise window** of its key
    (`revoke(..., compromised_from=)` / `rotate_key(..., compromised_from=)`). A revocation WITHOUT a declared window
    leaves earlier records admitted: revoking alone does not say they were forged.

  NEGATIVE records are the exception to the self-issuance rule: a failing check, an UNKNOWN channel entry, an 'outside' or
  'unknown' report, or a FALSIFIED or UNKNOWN envelope only ever lower, so they are admitted from the result's own
  executor.
- **Consumer rules.** Positive backing needs the factor's role (`FACTOR_ROLES`):
  - numerical UQ: NUMERICAL_VERIFICATION or UNCERTAINTY;
  - measurement UQ: MEASUREMENT;
  - parameter and model-form UQ: UNCERTAINTY.

  An attested failing check caps the factor its level projects to. A failing check that declares NO level (a
  conservation balance, a failed oracle comparison) caps every factor of the attesting role (NUMERICAL_VERIFICATION:
  verification and independent routes; VALIDATION: validation). An attested UNKNOWN entry caps its channel. An
  attested 'outside' or 'unknown' applicability report counts on the result its attestation binds, whatever digest
  the report itself carries, and `attest_record` refuses a report naming a different result. An attested FALSIFIED
  envelope about a subject's result is a defeater whatever node name or claim id it carries. The
  ledger itself does not narrow roles by record level (residual); the consumer does.
- **Durable campaign** (`claims.durable_campaign`).
  - Exposure clock, falsifier registry, multiplicity and novelty are journaled as EXPOSURE attestations, with the heads
    after each operation, and are replayed on resume.
  - The campaign identity is namespaced by ledger id and root.
  - One live object exists per identity; `start` refuses an existing journal and the multiplicity one-ledger rule
    applies.
  - Campaign-layer records (journal entries, manifests, approvals, pre-registration revisions, abstentions) signed
    inside a declared compromise window are not trusted; `resume` refuses a tainted journal. `declare_compromise`
    declares a window on ANY key of an issuer, retired ones included; a window only widens.
  - Gates and verifiers read only the campaign's own ledger (`campaign.ledger`); `verify_passport` takes the
    operator's TrustAnchor and re-derives discipline, status, verdicts, novelty, credibility (re-run) and the Red Team
    outcome (from its attestation), bound to the registered hypothesis and the campaign context. Not re-derived: the
    manifest digest, the claim digest and the screening summary; the envelope binds to the hypothesis by route label.
  - A campaign has exactly one owner: the issuer of its single EXPOSURE start. `resume` refuses another issuer and a
    ledger holding a second start (a fork or a squat). The first start wins, so who may hold EXPOSURE is a root
    decision.
  - The journal is read only from the owner's EXPOSURE entries in the start's context; foreign entries are listed and
    ignored. A resume that fails mid-replay releases the half-built object.
  - `resume` requires the operator's stored anchor (`campaign.anchor` after the last operation), so a dropped tail is
    refused.

## TRUST_REPAIR_DEPENDENCY_CANDIDATE

PR #123 is not used, copied or depended on. Two candidates stay in that lane:
- durable, signed SRIA admission declarations (`sria/admission.py:45-47`, certified);
- binding ValidationCheck itself to a result (`validation.py:249-252`, certified).

This campaign binds checks to results from OUTSIDE the certified record, through attestations.
