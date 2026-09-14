# Branch protection for certified merges

Repository files cannot protect `main`. Every check in
`.github/workflows/recertify-hardened-core.yml` and `.github/workflows/tests.yml`
is advisory until GitHub is configured to require it. When this document was
written, `main` had **no branch protection and no ruleset**. A pull request
could merge with its recertification red, still running, or never started.

Configuring this needs repository administration. No workflow in this
repository changes these settings. `python -m tools.certification.branch_policy
--repository sharq-labs/forge` reports whether they are in force, and so does
the **Branch Policy** workflow on every push to `main`. That workflow stays red
until the ruleset below exists.

## Two facts the policy is built on

1. **A skipped required check counts as passing.** Every job in both workflows
   is conditional on how the change was classified. Requiring
   `verify_certificate_child` or `certificate-child` directly does not protect a
   core pull request. On its source commit those jobs are *skipped*, so the
   pull request is mergeable even when `certify` failed. Each workflow
   therefore ends in an unconditional aggregate gate (`if: always()`). The gate
   knows which jobs had to succeed for the classified mode, and those two gates
   are the checks to require.
2. **Only merge commits preserve certificate lineage.** The certificate child
   is verified to be the one-parent child of the measured source commit, and to
   carry the exact bytes the certify run uploaded. A squash or rebase merge
   writes different commits. `main` would then carry a certificate naming a
   commit that is not in `main`'s history.

## Required ruleset (Settings → Rules → Rulesets → New branch ruleset)

| Setting | Value |
|---|---|
| Ruleset name | `certified-main` |
| Enforcement status | **Active** |
| Bypass list | **empty** (no repository admins, no maintainers, no apps) |
| Target branches | Include default branch (`main`) |
| Restrict deletions | **on** |
| Block force pushes | **on** |
| Require a pull request before merging | **on** |
| → Required approvals | ≥ 1 |
| → Dismiss stale pull request approvals when new commits are pushed | on |
| → Require review from Code Owners | recommended, with a `CODEOWNERS` entry covering the `certification_control` scope area |
| → Require approval of the most recent reviewable push | recommended |
| → Allowed merge methods | **Merge** only |
| Require status checks to pass | **on** |
| → Require branches to be up to date before merging | **on** |
| → Status checks (source: GitHub Actions) | `recertification-gate`, `tests-gate` |

Add both status checks with the **GitHub Actions** app as the source. That
stops another integration from posting a status with the same name.

As JSON, for `POST /repos/sharq-labs/forge/rulesets`:

```json
{
  "name": "certified-main",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 1,
      "dismiss_stale_reviews_on_push": true,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": false,
      "allowed_merge_methods": ["merge"]
    }},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": true,
      "required_status_checks": [
        {"context": "recertification-gate", "integration_id": 15368},
        {"context": "tests-gate", "integration_id": 15368}
      ]
    }}
  ]
}
```

Also recommended, in Settings → General → Pull Requests: disable *Allow squash
merging* and *Allow rebase merging*. The ruleset already restricts merge methods
on `main`; these settings make that visible everywhere else.

## What each gate requires

The logic lives in `tools/certification/recertification_scope.py`
(`recertification_gate_problems`, `tests_gate_problems`) and is unit-tested in
`tests/test_recertification_scope.py`.

| Head classified as | `recertification-gate` passes only if | `tests-gate` passes only if |
|---|---|---|
| ordinary pull request | `classify` succeeded and every other job was skipped | `repo-layout`, `fast` (3.11 and 3.12), `mutations`, `scientific` succeeded |
| core source commit | all eight source gates and `certify` succeeded | `repo-layout` succeeded and the heavy jobs were skipped (the recertification gate owns this head) |
| certificate-only child | `verify_certificate_child` succeeded (lineage, provenance, stored certificate, self-checks, clean tree) | `certificate-child` succeeded (lineage, stored certificate, self-checks, clean tree) |
| push to `main` | — (the workflow does not run on push) | `repo-layout`, `fast`, `mutations`, `scientific` succeeded |

On a core pull request the source commit is never the head that merges. When
`certify` succeeds it pushes the certificate-only child, which becomes the head,
and both gates run again on that child. With *require branches to be up to
date*, the child must also sit on the current `main`. Otherwise the certify
job's merge-preview check refuses, and recertification runs again after the
update.

## What this does not cover

- **A pull request can edit its own workflows.** `pull_request` workflows run
  the YAML from the pull request's merge preview. A change that weakens a gate
  is recertified by the weakened gate. The certificate pins the control plane,
  so the change is visible in the certificate diff and in the
  `certification_control` area. Only required human review of those paths
  (Code Owners) stops it from merging.
- **Bypass actors cannot be read by CI.** The default token can read which rules
  apply to `main`, but not who may bypass them. The branch policy check reports
  this as *unverified*, never as satisfied.
