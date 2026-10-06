# Branch protection for local-assurance merges

FORGE intentionally does **not** use automatic GitHub Actions status checks as
scientific attestation. The authoritative assurance path is local:

```text
exact source commit
  -> local source gates (Python 3.11 + Python 3.12)
  -> frozen evidence manifest
  -> hardened-core assurance record
  -> Core certificate
  -> certificate-only child
  -> local child/self-check verification
  -> SAFE_TO_PUSH: YES
```

The executable entrypoint is:

```bash
python -m tools.certification.local_assurance
```

See `docs/assurance/LOCAL_ASSURANCE.md` for the operator procedure.

## What GitHub does and does not attest

GitHub hosts the repository, pull requests, reviews and merge history. The
workflows under `.github/workflows/` are manual-only reference/fallback
workflows. There is no `pull_request`, `push` or `schedule` trigger in the
authoritative configuration.

GitHub therefore does **not** attest that FAST, SCIENTIFIC, regression or
mutation gates ran. That claim comes from the local assurance receipt embedded
into the certificate's assurance record and bound to the exact source commit.

This is a deliberate trust model. It must not be described as independent
third-party execution: the trust root is the controlled local workstation and
the recorded runtime/evidence identity.

## Required branch rules

Repository files cannot enforce branch rules. Configure them in GitHub
(Settings -> Rules -> Rulesets) where the repository plan supports them.

| Setting | Required value |
|---|---|
| Target | default branch (`main`) |
| Enforcement | active |
| Require pull request before merging | on |
| Required approvals | >= 1 |
| Dismiss stale approvals | recommended |
| Code-owner review for certification control | recommended |
| Allowed merge methods | **merge commit only** |
| Block force pushes | on |
| Restrict branch deletion | on |
| Required GitHub status checks | **none** |

Do **not** add `tests-gate` or `recertification-gate` as FORGE-required
checks. They are not the authority in the local-only model.

A minimal ruleset shape is:

```json
{
  "name": "forge-main",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": ["merge"]
      }
    }
  ]
}
```

Exact GitHub ruleset fields can evolve; the normative FORGE requirements are
the table above, not the example JSON.

## Certificate lineage still matters

Local-only execution does not weaken certificate lineage. A hardened-core
certificate is still committed as a certificate-only child:

- exactly one parent;
- parent is the measured source commit;
- only `certification/current_core_v2.json` changes;
- commit subject is `certification: recertify hardened core`;
- assurance source/parent fields equal that parent;
- local evidence manifest digest is embedded in the assurance record;
- the final local verification runs the deferred certificate/freeze self-checks.

Squash or rebase merging rewrites commits and can break this relationship, so
merge commits remain the required merge method for certificate lineage.

## Operator rule

A branch is not ready merely because its tests were run at some point. The
operator must run local assurance on the exact commit that will be certified.
After the certificate-only child is committed, the operator must run:

```bash
python -m tools.certification.local_assurance verify
```

Only the explicit terminal result:

```text
LOCAL_ASSURANCE: PASS
SAFE_TO_PUSH: YES
```

is the FORGE local merge/push signal.
