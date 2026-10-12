> Historical design record. Passes 5–6 and LOCAL_ASSURANCE.md define the current contract.
> Formal has no copied .git; V4 has sealed copied .git. The current index stores entries and digest, not cached bytes or redundant name tuples.

# Local Assurance optimization pass 4 — static contract

Source HEAD: 8d5eed3f47a0490d481b7ff5c9927f2f944096db. Accumulated Pass 2–4
edits remain uncommitted. Implementation and hostile static review only.
TESTS_RUN: 0. ASSURANCE_RUN: NO. FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
No project execution/imports, benchmarks, certification or publication.

## Pristine storage and identity

PristineIndex retains frozen Entry metadata and SHA-256 values in read-only
mappings, sorted file/directory names and deterministic manifest digest. No file
bytes are retained. Metadata is O(entries); content hashing/copying streams in
1 MiB chunks. No optional cache is introduced, so cache hits, available RAM and
cache eviction cannot change evidence behavior. Seed remains the sole byte source.

Seed metadata identity covers the whole topology, types, modes, file sizes and
link counts. File-content identity is a complete SHA-256 scan. Worker identity
uses independent complete structural comparison and complete SHA-256 scans.
Read-only seed permissions limit accidental writes but grant no identity proof.
Every pre-attempt boundary and pre-repair boundary enforces complete seed identity.
Any mismatch poisons the shard before repair and before another attempt. Each
restored seed file is opened with O_NOFOLLOW, checked by fstat, streamed and hashed
against the indexed size/digest. Failure invalidates the round; no worker fallback
exists. Unrelated same-size worker corruption still triggers full-hash detection,
one sparse repair and complete verification again.

The complete identity is continuously enforceable at explicit boundaries, not
continuously guaranteed by permissions. Trusted controlled-host assumptions
exclude external writers during these checks; this is not a malicious-UID sandbox.

## Git sealing and independent storage

All .git remains independently copied. Objects, refs, HEAD, index, config, hooks,
packed refs and shallow state stay under complete manifests. No hardlinks,
alternates, shared object store, shared refs or worktree common area are created.
The same UID can reverse read-only modes, so shared Git immutability is not proved.

Initial seed admission refuses external common/Git/storage pointers, both kinds
of alternates, worktree config/admin state, include/includeIf (case normalized),
core worktree/hooks/fsmonitor/attributes/excludes/ssh/pager pointers, filter/diff/
merge drivers and credential helpers. Grafts and loose or packed replace refs
are refused because they can rewrite historical reads. Config parsing failures
also refuse. Normal remote URLs remain copied for repository identity; this
contract does not authorize network Git operations. Shallow history is copied,
not synthesized: missing required historical objects must still fail guards.

Every target starts with inherited GIT_* variables removed, including directory,
index, object, alternate, config-key/count, ceiling and trace injections. Explicit
system/global config paths are /dev/null with GIT_CONFIG_NOSYSTEM=1. An owned empty
Git template area prevents host templates installing hooks in synthetic repos;
command-scope core.hooksPath=/dev/null disables inherited local hooks. safe.directory
host overrides disappear with host config; same-user private copies use ordinary
Git ownership checks. We do not set GIT_DIR or GIT_WORK_TREE: fixture tests create
and mutate nested synthetic repositories using cwd discovery. Explicit Git/Python
environment overrides constructed inside tests retain their existing semantics.
No host config silently supplies scientific identity or historical evidence.

Git configuration is parsed conservatively for supported baseline syntax;
unsupported/malformed/oversized config refuses rather than bypassing sealing.
Section admission rejects trailing whitespace and deprecated dotted forms that
ConfigParser would otherwise interpret differently from Git.
Target code can explicitly override environment or create new config. This seal
prevents accidental host inheritance, not arbitrary hostile code escaping its UID.

## Environment classification

| Classification | Contract |
| --- | --- |
| Explicitly required/set | sys.executable target interpreter; repository pytest pythonpath/addopts; Linux process primitives; owned TMPDIR/TMP/TEMP; Git system/global null config; empty Git templates; inert hooks; PYTHONNOUSERSITE=1 |
| Explicitly neutralized | inherited GIT_* redirects/config/helper/trace settings; PYTHONPATH/PYTHONHOME/PYTHONSTARTUP/PYTHONUSERBASE; PYTEST_ADDOPTS/PYTEST_PLUGINS |
| Inherited by trusted-toolchain contract | PATH and external tool identities; virtualenv; installed pytest plugins and PYTEST_DISABLE_PLUGIN_AUTOLOAD; provider/solver/scientific variables; locale; HOME/XDG configuration for non-Git tools; other runtime settings |

Repository pyproject provides import paths and importlib collection. Existing
tests constructing subprocess PYTHONPATH continue to do so relative to their
worker. We do not disable installed plugin discovery or change provider settings.
The installed toolchain, provider configuration and PATH remain controlled-run
inputs; this patch does not establish hermetic scientific execution.

## Dedicated process ownership

Local Assurance already launches each Formal/V4 shard as its own interpreter.
Targets require Linux main-thread operation, exactly one /proc kernel task,
default/unblocked SIGCHLD, no existing children and no pre-existing subreaper role.
The process-local lock rejects concurrent targets. Detected ambiguity poisons the
process and workspace, records diagnostics and retains storage before any launch.
No new supervision framework is introduced.

The shard installs and verifies its own subreaper role before Popen. An ancestor
subreaper does not compete while the dedicated shard is alive. A nested descendant
subreaper is still owned: killing/reaping its ancestors eventually adopts remaining
children. New sessions/process groups, double forks and daemonized descendants do
not establish a new storage owner. All owned direct children are enumerated across
kernel task child lists, killed and reaped until enumeration is empty. Zombies
must be reaped; PID reuse safety relies on no competing reaper or child creation in
the shard. Kernel task/SIGCHLD checks strengthen that assumption but cannot detect
all injected native code or malicious signal-state changes after admission.

Popen constructor failure, communicate timeout and signal interruption enter drain
once ownership setup is active, even without an assigned Popen object. Creation
itself is not bounded by communicate timeout; hard termination can leave retained
scratch and cannot certify success. Repeated SIGTERM is ignored during drain.
An exception while setting that drain handler is itself unproven quiescence.
Drain/release failure refuses reuse and retains storage. No restoration or deletion
of uncertain workers is permitted; the parent honors retained workspace directories.

## Descriptor and runtime lifetime

Hash/copy files, directory scandir handles, config/packed-ref readers and telemetry
writers use context-managed ownership. The index owns no live file handles.
Seed copy uses builtin open with an O_NOFOLLOW opener, which owns the descriptor
through errors. Popen explicitly closes inherited descriptors and passes none;
stdout/stderr close in nested finally blocks even if one close fails. Descendant
reaping precedes workspace repair and owned runtime cleanup. Runtime path/parent
inode/type checks reject substitution before recursive cleanup. Ambiguous drain
retains runtime alongside worker. Worker, seed and parent cleanup remains fail-closed.

## Diagnostics and source-only specifications

Additive counters report seed/worker disk bytes, seed/worker hash file counts,
entries/files structurally scanned, restoration bytes/files, Git files/bytes
processed and retained workers for uncertain ownership. Cache bytes served are
zero by construction. Git counters count processing work across checks/repairs,
not unique baseline size. Counters are best-effort, not gate inputs; both authority
flags remain false. Diagnostic accounting failure cannot change identity checks.

Tests are specifications only: no-cache restoration; seed byte/deletion/extra/type/
mode/symlink/hardlink refusal before repair; Git environment injection and host
config neutralization; dangerous local config/alternates/history refusal; detected
owner ambiguity and next-attempt refusal; descriptor/pipe/runtime cleanup; retention;
non-authoritative counters and unavailable accounting. Prior specs remain unless
structurally superseded: Pass 3's zero-repeated-seed-hash assertion is replaced by
complete seed SHA identity, required by the filesystem-source architecture.

Current operation counts are in the Pass 3 document's Pass 4 update. No executed
verification, speedup, runtime percentage or measured memory claim is made.

## Remaining risks and pass 5

Operating-system lifecycle and compatibility remain untested. Full byte hashing
still performs O(total bytes) boundary work; metadata remains O(entries). Dedicated
process/toolchain assumptions do not protect against arbitrary external same-UID
writers, injected native reapers or target code intentionally rewriting its own
environment. Installed plugins and external providers remain trusted semantics.
Future pass 5 should statically audit Git dialect/config and environment contracts,
cleanup ownership and test specifications; execute tests or measurements only after
an explicit user authorization supersedes the current execution prohibition.
