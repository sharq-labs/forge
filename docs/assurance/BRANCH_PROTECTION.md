# Local assurance merge governance

GitHub required status checks: **NONE**.

"GitHub does not attest test execution. Scientific assurance is produced
locally and bound to the exact commit by the local assurance receipt."

Local assurance is not an independent third-party execution environment.
Its trust root is the controlled local workstation and its recorded runtime
identity. A receipt hashes evidence; it is not a signature or a defense against
an owner who fabricates execution evidence or changes the verifier.

All workflow files remain in the certified control plane as dormant manual
references, with workflow_dispatch only. No PR, push, schedule or main event
runs GitHub assurance automatically. Manual reference results are not local
assurance receipts and cannot promote a local certificate.

Repository files do not configure GitHub settings. An administrator must remove
legacy required checks from both classic protection and rulesets. The read-only
branch_policy command reports any required GitHub check as a policy violation.
No remote settings have been changed by this implementation.

Keep an active ruleset on main requiring a PR and at least one human approval,
dismissing stale approvals, blocking force pushes and main deletion. Require
human review of certification-control changes; Code Owner review is recommended.
Allow merge commits only for certified changes: squash/rebase rewrites the
verified source/child history. Never automatically push from the local runner.

Before push/merge, run `python -m tools.certification.local_assurance verify` on
the clean certificate child. It must end with LOCAL_ASSURANCE: PASS and
SAFE_TO_PUSH: YES. A source-phase receipt alone is insufficient. If main moves,
reconcile the source, rerun all gates and generate a new child. Verify any merge
preview preserves the measured certified bytes using the existing lineage
merge-preview check. After merge, run local assurance for any changed merged
bytes; GitHub performs no merged-tree test execution.

See [LOCAL_ASSURANCE.md](LOCAL_ASSURANCE.md) for the evidence protocol.
