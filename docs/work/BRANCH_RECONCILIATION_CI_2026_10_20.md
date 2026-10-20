# Branch reconciliation and post-merge CI investigation

Examined main: `67585300b092e2ffa543deccf39cfae0efe6e9b1` (PR180).
This is a bounded investigation, not certification or scientific validation.

## Post-merge workflows

Live GitHub API reads in this session found:

| Workflow | Run | Evidence |
|---|---|---|
| Tests | [39488053735](https://github.com/sharq-labs/forge/actions/runs/39488053735) | scope, reproduce, benchmark, repository layout and tests-gate failed, each with an empty steps array; scientific, certificate-child, mutations and FAST skipped |
| Branch Policy | [39488053796](https://github.com/sharq-labs/forge/actions/runs/39488053796) | job118853558670 failed, empty steps array |

Fetching logs for branch-policy job118853558670 and scope job118853560388
returned HTTP404 BlobNotFound. The available connector rejects check-run
annotations endpoints. The browser is signed out and shows404 for the private
run. No checkout or test execution is evidenced by these jobs. Root cause is
UNVERIFIED; no billing, quota, runner or YAML diagnosis is asserted. The owner
was asked for the run's Annotations message. Workflow reruns and hosted tests
are NOT RUN during this investigation; repeated reruns without a diagnosis
would not resolve the evidence gap.

`branch_policy.py` has stale explanatory text saying automatic workflows are
disabled, while current workflows and BRANCH_PROTECTION.md enable automatic
runs. That stale comment is not evidence of the job failure: the available job
responses contain no step execution evidence.
Changing this certification-control file requires its own reviewed scope.
No workflow, required-check rule, certificate or test was weakened.

## Next historical branch

Read-only independent inventory found20 distinct residual tips in15 maximal
ancestry groups, excluding preserve/*, wip/* and ancestors of main. Nineteen
tips have branch-owned changes that trigger the current recertification
classifier. This is classification, not proof that their code is safe to adopt.

The remaining tip `c4b9d9500807a33a1209cffeef83303ca16c8656`
(`codex/multidomain-science-hardening`) adds seven agent/configuration files.
Current .gitignore excludes AGENTS.md, .agents/ and .codex/. Its historical
manual-only CI instruction conflicts with current automatic-CI policy.

Proposed disposition: preserve its exact delta in
[the archive](../archive/branch_deltas_2026_10_20/multidomain-science-hardening/README.md),
without installing configurations or activating historical instructions.
This is preservation, not adoption of the agent settings. The archive-only
merge commit is `ce32f6a613e88dd908d894a465ea03e01b6fcf1e`.
Its parent tree is preserved except for the two new archive files.
The patch is42088 bytes, SHA256
`409329d709dce4878fbe1f7269709b16b22254e365111e65c9156894e498046b`.
Raw patch context whitespace is intentional and must remain byte-identical.

After this proposed reconciliation,19 tips in14 maximal ancestry groups would
remain. Their implementation adoption stays subject to source reconciliation,
targeted tests, scientific review, existing owner decisions and applicable
OD-3. Do not merge old certificates as substitutes for a current certificate.

The candidate remains pending concrete owner PR approval. No freeze, formal
Genesis measurement, dependency installation or hardened recertification ran.
