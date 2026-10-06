# Local-only assurance protocol

The authoritative entry point is `python -m tools.certification.local_assurance`.
It runs native processes on the owner's workstation. Prefer Linux under Ubuntu
WSL with separate Python 3.11 and 3.12 virtual environments, each installed with
`python -m pip install -e ".[dev,mcp,oracles]"`; install ngspice in that Linux
environment. Both editable installations and engcore imports must resolve to the measured checkout. Use a standalone Git clone inside Linux: the certified V4
mutation copier expects a .git directory and linked worktrees are refused.
Run the entry point inside that environment and pass absolute
venv Python paths using --python311 and --python312. There is no implicit runtime
installation, dependency substitution, remote execution or Python 3.14 fallback.
A missing interpreter, dependency/version, pip consistency or ngspice refuses.

## Measurement

Commit source changes first: the runner refuses a dirty/untracked checkout and
raw tracked bytes differing from committed blobs, including CRLF normalization.
Run:

```sh
python -m tools.certification.local_assurance run   --python311 /path/to/venv311/bin/python   --python312 /path/to/venv312/bin/python --workers 8
```

Functional gates execute sequentially in the measured checkout. Existing formal shards run concurrently with one another, followed by concurrent V4 shards, bounded by --workers; each has its own scratch tree and evidence directory. Every shard retains its serial control/mutation execution. FAST/SCIENTIFIC use
xdist loadfile; campaign stays serial; mutation runners isolate modified copies
outside the source repository. Source HEAD and raw-byte cleanliness are checked
before and after every command and gate. Runtime/dependency identity is checked
after each gate. This is boundary inspection, not continuous filesystem
surveillance or tamper-proof execution against the workstation administrator.

The gate set is unchanged: dependency reachability and FAST on 3.11 and 3.12;
SCIENTIFIC, campaign and false-confidence regression on 3.12; all four formal
shards, all eight V4 shards and the complete trust mutation population. Existing
hardened-suite exclusions/skip ceilings are preserved. Certificate-dependent
self-checks are deferred only to the certificate child, exactly as previously.
Population IDs, definitions, shard union/disjointness, controls and verdicts
are rederived by the existing mutation and assurance readers. No count is used
as a substitute for population coverage.

Evidence lives under `.forge/assurance/<SOURCE_SHA>/` (ignored), or an explicit
FORGE_LOCAL_EVIDENCE_DIR base. Existing directories are refused, never erased.
Logs and partial evidence are retained on failure; there is no PASS receipt for
a partial run. Use a new evidence base to retry while preserving old artifacts.
The canonical receipt binds source SHA/tree, origin identity, UTC timestamps,
OS, interpreter executable hashes/versions, each pip-freeze digest, ngspice
version, pyproject/control digests, command plans/results/timings, all gate
clean-tree records, population evidence and SHA-256 of every source evidence
file. Deterministic encoding does not mean two runs have identical timestamps.

## Certification and promotion

The old GitHub assurance schema /5 and environment /4 keep their old semantics
and GitHub provenance verifier. New local assurance uses /6, environment /5,
and explicit provenance_mode=local. Old certificates are never reclassified
as local. The certificate envelope remains compatible; the changed embedded
assurance semantics are versioned. No historical certificate is rewritten.

After all source gates pass:

```sh
python -m tools.certification.local_assurance write-certificate
# Review and commit ONLY certification/current_core_v2.json using the existing
# reserved certificate-child subject printed by recertification_scope.
python -m tools.certification.local_assurance verify
```

The official builder embeds the full local receipt and its SHA-256 in the
certificate. The child must have exactly one parent, the measured source, and
modify only the certificate. Verification checks lineage, content/scope,
receipt/evidence hashes and rederives assurance from the files. It then runs all
deferred self-checks using the measured 3.12 environment; each must be reported
passed, not skipped. A separate child-bound promotion record hashes that report
and transcript, avoiding a receipt/certificate hash cycle.

Only the final verify command can print LOCAL_ASSURANCE: PASS, SOURCE_SHA,
RECEIPT_SHA256 and SAFE_TO_PUSH: YES. Source measurement and certificate writing
print REFUSED / SAFE_TO_PUSH: NO until child promotion finishes. They never
commit, push, open a PR or merge. Keep the evidence directory with the controlled
workstation; a verifier without the original evidence refuses. Receipt hashes
are content bindings, not independent proof that a privileged owner ran tests.
