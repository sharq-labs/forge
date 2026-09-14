# Core certification

## The one command

```bash
python -m tools.certification.core_certificate --verify
```

Exit 0 means the checked-out tree is byte-for-byte the tree
`current_core_v2.json` certifies. Any other exit means it is not, and the
output names which files were added, removed or modified — not just that two
digests differ.

The same check runs as an ordinary test, so a certificate that stops
describing the tree turns a suite red rather than sitting quietly:

```bash
python -m pytest tests/test_core_certificate.py
```

## The other commands

```bash
python -m tools.certification.core_certificate --manifest   # print the manifest
python -m tools.certification.core_certificate --build      # write a certificate
```

`--build` refuses a dirty tree. A certificate names a commit, and one built
from uncommitted edits describes a tree nobody can check out. `--allow-dirty`
produces a diagnostic certificate, which marks itself as one and which
`--verify` refuses to accept as a certificate.

`--verify` compares **content** by default and reports the commit relationship
informationally, because a certificate is committed as a child of the commit
whose tree it certifies — so HEAD is normally that child. The content
comparison is unaffected: `certification/` is outside certified scope. Pass
`--require-commit` to demand HEAD be the certified commit exactly.

`--verify` also refuses a certificate **written under an older scope table**.
Such a certificate still agrees byte-for-byte over the areas it names, and says
nothing about an area added since — the certification control plane, for
instance. `--any-scope` diagnoses one without refusing it for that reason; CI
never passes it.

## Lineage, provenance, and the certificate child

Byte agreement does not say which commit a certificate is about. The
certificate-only child that the recertify workflow's certify job pushes is
verified with:

```bash
python -m tools.certification.certificate_lineage verify-child [--merge-preview SHA]
python -m tools.certification.certificate_lineage verify-provenance --repository OWNER/REPO
```

`verify-child` requires one parent, a change to the certificate and nothing
else, and `repository.commit`, `assurance.source_commit`,
`assurance.environment.source_commit`, `assurance.lineage.source_commit` and
`assurance.lineage.certificate_parent` all present and all equal to `HEAD^`. It
re-validates the `forge.core_hardening_assurance/3` record against the tree —
formal mutation population and exact shard coverage, trust-hardening population,
functional gate evidence, dependency manifest, control-plane digest.
`verify-provenance` asks GitHub whether the run the certificate names ran the
recertify workflow for `HEAD^`, finished every source gate and certify
successfully, and uploaded exactly these certificate bytes. A certificate that
did not come out of that job cannot pass it.

Which changes need recertification is decided by one classifier, derived from
the scope table, and called by both workflows:

```bash
python -m tools.certification.recertification_scope explain <path> ...
```

Every source gate ends with `python -m tools.certification.assert_clean_tree`,
which fails on any modified, added or deleted repository file, including a
line-ending rewrite `git status` does not report. The merge policy these checks
rely on — and which only a repository administrator can configure — is in
`docs/assurance/BRANCH_PROTECTION.md`.

## What is certified

See `scope` in the certificate. The criterion for inclusion is narrow: an area
is in when a silent edit to it would change **what a verdict means**, rather
than change an answer.

| Area | Class | What |
|---|---|---|
| `core` | CORE_CERTIFIED | `src/engcore/scientific/**` — the contracts |
| `trust_registry` | CORE_CERTIFIED | `src/engcore/domains/__init__.py` — the declarations the core verifies against |
| `evidence_identity` | CORE_CERTIFIED | `src/engcore/adequacy/**` — evidence pairing |
| `inference_admission` | CORE_CERTIFIED | `src/engcore/inference/**` — the admission invariant |
| `runtime_data` | RUNTIME_SUPPORT | `src/engcore/data/**` — what a data reference resolves through |
| `harness` | HARNESS | the mutation runner and the four suites it runs |
| `certification_control` | CERTIFICATION_CONTROL | the verifier and every `tools/certification/*.py` module, the two certification workflows, the self-check test modules, the freeze probe — each file with its own reason |
| `runtime_dependencies` | RUNTIME_ENVIRONMENT | `pyproject.toml` — what every gate installs and how pytest is configured |

Domain solvers, the MCP boundary, applications, benchmarks and experiments are
out of scope, and the certificate says so in `scope.out` with a reason for each.

## The digest

Per file, SHA-256 over exact bytes. Per area, SHA-256 over
`path + NUL + file digest` in path order. Overall, SHA-256 over
`area name + NUL + area digest` in name order. Repository-relative POSIX paths,
sorted by UTF-8 path bytes, `__pycache__` and `*.pyc` excluded, symlinks
refused, **line endings not normalized**.

The algorithm is implemented in `tools/certification/core_certificate.py` and
documented in its module docstring and in the certificate's own
`digest_algorithm` block.

## V1

`current_core_v1.json` is a **historical certificate** and is kept unchanged.
It certifies commit `be57bf4`, and its algorithm is recoverable and was
recovered: it is written out in its own
`verification.how_to_reproduce_the_certified_tree`, and running it against
`be57bf4` reproduces its stored `82558f5b…` exactly, over 47 modules.

What V1 lacked was not an algorithm but anything that ran one. There was no
script, no command and no test, so it went two sprints out of date without
anything saying so. That is the gap V2 closes.

V2's area digests use repository-relative paths where V1 used paths relative to
`src/engcore/scientific`, so the two numbers are not comparable by
construction. The certificate records `v1_continuity.v1_compatible_core_digest_now`
— the core tree recomputed exactly V1's way — so the relationship between them
is a number rather than a claim.
