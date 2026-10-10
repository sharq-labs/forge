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
  - numerical → NUMERICAL_VERIFICATION;
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

### Other registries
- Risk policies: `claims/credibility_vector.py:757-790`, process-global, stricter-only.
- Domain, oracle, route and threshold pins: source constants, certified.
- Bundle manifests (`mcp/bundle.py`, `engineering/bundle.py`): unkeyed. Out of scope.

## The new authority layer (`engcore.authority`, non-core)

- **Owner and dependency.** The layer is owned by `engcore.authority`, imported by `claims` and `blindfold`, and it
  imports nothing above `engcore.authority`. It depends on the optional `[authority]` extra (`cryptography`, ed25519). It
  does not create a second evidence model: it signs and orders DIGESTS of the existing records.
- **AuthorityLedger.** One append-only, hash-chained ledger of signed events: GENESIS, REGISTER, SET_ROLES, ROTATE,
  REVOKE and ATTEST.
  - Administrative events are signed by the root key fixed at genesis.
  - ATTEST is signed by the issuer's key. It is admitted only if, at that sequence, the issuer exists, is not revoked,
    holds the role, and the signing key is the issuer's active key.
  - Persistence is a JSONL file with fsync. On load every signature, link and state transition is re-verified, and the
    ledger must extend the consumer's pinned `TrustAnchor`: ledger id, root key, profile, and a (sequence, head) it
    already saw.
- **Profiles.** A ledger is created `test` or `production`. A production ledger refuses test-class keys. A consumer that
  requires `production` refuses a test ledger. No test key can become a production key.
- **Key material.** `KeyProvider`:
  - `EphemeralKeyProvider` is test class and in memory.
  - `DirectoryKeyProvider` is production class. It reads 0600 PEM/secret files from a directory outside the repository
    checkout and refuses anything group- or world-readable.
  - Private key material is never committed.
- **Attestation.** An attestation binds:
  - the record kind and schema;
  - `record_digest` and the full record dict, so that the ledger itself holds negative records;
  - `subject_digest` and `subject_output`;
  - `receipt_digest` (the EXECUTOR attestation of the NodeReceipt that produced the subject);
  - `context_digest`, the role and the issuer.
- **Evidence verification refuses:**
  - an unknown or revoked issuer, a wrong role, a retired or substituted key, or a bad signature;
  - a wrong result digest or a receipt that does not contain it;
  - a receipt not attested by an EXECUTOR issuer, or attested after the evidence;
  - a wrong context;
  - **self-issuance**: an evidence issuer that is the executor issuer of the subject's receipt.

## TRUST_REPAIR_DEPENDENCY_CANDIDATE

PR #123 is not used, copied or depended on. Two candidates stay in that lane:
- durable, signed SRIA admission declarations (`sria/admission.py:45-47`, certified);
- binding ValidationCheck itself to a result (`validation.py:249-252`, certified).

This campaign binds checks to results from OUTSIDE the certified record, through attestations.
