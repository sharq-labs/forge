# Local Assurance

FORGE's authoritative hardened-core assurance runs on a controlled local
workstation, not automatically on GitHub Actions.

The purpose is not to run a lighter test set. It is to execute the same
scientific source gates locally, record their exact evidence, bind it to the
source commit, and refuse to produce `SAFE_TO_PUSH: YES` if any required fact
is missing.

## Required environment

Use a Linux environment (WSL2 is suitable) with:

- Git
- Python 3.11
- Python 3.12
- `venv` support for both interpreters
- ngspice
- the repository checked out with a clean working tree

Python 3.14 results do not substitute for the required 3.11/3.12 gates.

Local environments, receipts and evidence are written below `.forge/`, which
is ignored by Git.

## 1. Prepare the local environments

From the repository root:

```bash
python -m tools.certification.local_assurance prepare
```

If the interpreters are not discoverable as `python3.11` and `python3.12`,
pass their executable paths explicitly:

```bash
python -m tools.certification.local_assurance prepare \
  --python311 /path/to/python3.11 \
  --python312 /path/to/python3.12
```

Preparation creates isolated environments below:

```text
.forge/venvs/3.11
.forge/venvs/3.12
```

and installs `.[dev,mcp,oracles]` into both.

## 2. Run source assurance

Commit the source change first. The working tree must be clean.

Then run:

```bash
python -m tools.certification.local_assurance run
```

The runner records the exact source SHA and tree SHA before execution and
refuses if HEAD moves or the tracked tree becomes dirty.

It runs:

- FAST on Python 3.11;
- FAST on Python 3.12;
- SCIENTIFIC on Python 3.12 with ngspice;
- campaign gate;
- false-confidence regression gate;
- all four formal mutation shards;
- all eight V4 mutation shards;
- trust-hardening mutations;
- a clean-tree proof after every gate.

The official gate evidence is stored under:

```text
.forge/assurance/<SOURCE_SHA>/evidence/
```

The runner freezes every official evidence file into an SHA-256 manifest,
builds the hardened-core assurance record using the existing assurance
validator, and then writes `certification/current_core_v2.json`.

A successful source run ends with:

```text
LOCAL_ASSURANCE: SOURCE_PASS
READY_TO_COMMIT_CERTIFICATE: YES
SAFE_TO_PUSH: NO
```

This is intentionally **not** the final push signal.

## 3. Commit the certificate-only child

Use the reserved subject exactly:

```bash
git add certification/current_core_v2.json
git commit -m "certification: recertify hardened core"
```

Do not include another path in this commit.

## 4. Verify the certificate child

Run:

```bash
python -m tools.certification.local_assurance verify
```

This step verifies:

- exactly one parent;
- certificate-only child shape;
- every parent-bound source field;
- certified bytes and current scope;
- the local assurance schema;
- the frozen local evidence manifest and every file hash;
- the assurance record against the source tree;
- all deferred certificate/freeze self-checks;
- a clean checkout before and after verification.

Only this output authorizes a push:

```text
LOCAL_ASSURANCE: PASS
SOURCE_SHA: <sha>
CERTIFICATE_CHILD_SHA: <sha>
RECEIPT_SHA256: <sha256>
SAFE_TO_PUSH: YES
```

Any partial run, missing runtime, test failure, mutation survivor, missing
evidence, modified evidence, dirty tree, changed source commit or failed child
check ends with:

```text
LOCAL_ASSURANCE: REFUSED
SAFE_TO_PUSH: NO
```

## Re-running a source

A previous assurance directory is never silently mixed with a new run. To
discard the prior local evidence for the same source and execute every source
gate again:

```bash
python -m tools.certification.local_assurance run --reuse
```

`--reuse` means "discard and re-run"; it does not reuse prior gate results.

## Trust model

Local assurance is strong evidence about **what ran on this controlled
workstation**. It is not independent third-party attestation.

The receipt records the source identity, runtime identities, gate durations,
evidence-manifest digest and certificate digest. For high-stakes releases,
independent reproduction can still be added as a separate scientific or
release-level assurance activity without making GitHub CI authoritative again.
