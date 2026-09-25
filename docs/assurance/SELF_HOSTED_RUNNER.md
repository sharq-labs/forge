# Self-hosted heavy CI runner (the owner's PC)

The expensive CI jobs can run on the owner's own machine instead of GitHub-hosted
runners. This page is the design, the threat model (including what it does **not**
protect against), the setup, and the operating procedure. Nothing here changes what
any gate measures, what evidence it uploads, or what `tests-gate` /
`recertification-gate` require.

## 1. What runs where

| Where | Jobs |
| --- | --- |
| **GitHub-hosted, always** | `scope`, `classify` (they decide the mode and the runner), `repo-layout`, `certificate-child`, `certify` (holds the `contents: write` token and pushes the certificate child), `verify_certificate_child`, `tests-gate`, `recertification-gate`, `branch-policy`, `select-runner` |
| **Heavy: the PC when selected** | Tests: `fast` (3.11, 3.12), `mutations`, `scientific`, `reproduce`, `benchmark`. Recertify: `fast311`, `fast312`, `scientific312`, `campaign312`, `regression312`, `formal_mutations_0-3`, `v4_mutations_0-7`, `trust_mutations`. Trust Mutations: `trust-mutations` |

Everything that mints or pushes trust (certificate builder, its push, provenance
verification, the merge gates) stays on GitHub-hosted runners. `tests/test_ci_self_hosted_scripts.py`
pins this: no trust-bearing job may take its runner from the classifier.

Job names, `needs:` lists, the `if: always()` gates and the evidence artifact names are
unchanged, so `recertification_scope`, `hardening_assurance` and the branch-policy check see
the same topology (`tests/test_recertification_scope.py` pins that too).

**Limit of what the PC's evidence proves.** The hosted `certify` job re-derives counts and
cross-file consistency from the evidence files (it checks, for example, that the four Python 3.12
gates resolved a byte-identical `pip freeze`, that the mutation populations are complete, and that
each gate's tree was clean at the source commit). It does **not** verify *where* those files were
produced, and the certificate records only `certify`'s own `RUNNER_OS`. A certificate minted from
PC evidence is therefore not distinguishable from a hosted one by its contents. The per-job
`runner-identity-<job>-<sha>` artifacts record the runner, but they are not bound into the certificate.
Binding them would change the certified assurance schema and is left as a recorded follow-up
(`docs/work/PROGRESS.md`), not done here.

## 2. How a heavy job chooses its runner

`classify` / `scope` run `python -m tools.ci.select_heavy_runner` and expose `heavy_runs_on` (a JSON
label array). Heavy jobs use `runs-on: ${{ fromJSON(needs.<classifier>.outputs.heavy_runs_on) }}`.

| `FORGE_HEAVY_RUNNER` (repository variable) | Event | Runs on |
| --- | --- | --- |
| unset / `github-hosted` (**default**) | any | `ubuntu-latest` |
| `self-hosted` | `push`, `workflow_dispatch` | `[self-hosted, linux, x64, forge-pc]` |
| `self-hosted` | `pull_request`, head repo = this repo, not a fork, author OWNER/MEMBER/COLLABORATOR | the PC |
| `self-hosted` | any other pull request / event | `ubuntu-latest` (coverage kept, PC untouched) |
| anything else | any | **the workflow fails**: an unknown value is never guessed |

The default is GitHub-hosted so the change that introduced this runs before any runner exists.
If the classifier fails, the heavy jobs are skipped and both gates (which require the classifier to
have succeeded) fail: nothing skips to a pass.

**This selector is routing, not the security boundary** (section 4): a fork's pull request runs the
workflow file of the fork's own merge commit and could name the PC's labels itself.

### When the PC is off, restarted or disconnected

With `self-hosted` selected the job is **never re-routed**. It waits in GitHub's queue and the required
checks stay pending (not green); GitHub fails a job that stays queued for 24 hours. With the optional
secret `RUNNER_STATUS_TOKEN` (fine-grained, this repository only, *Administration: read*) the selector
instead fails immediately with:

> no online runner carries [...]. The PC is off or its runner service is stopped. Start it, or set
> FORGE_HEAVY_RUNNER to 'github-hosted' ... Jobs are NOT re-routed automatically.

With the same token it also **requires** the fork-approval setting to be `all_external_contributors`
(section 4). Without the token neither check runs and the run prints a notice saying so. The token is
visible to same-repository pull-request code in the step that uses it, like any repository secret;
grant read access only.

Falling back is an explicit administrator action (`gh variable set FORGE_HEAVY_RUNNER --body github-hosted`)
and is visible in every run: each heavy job uploads `runner-identity-<job>-<sha>` naming the runner,
environment, OS, kernel, CPU/RAM, Python, git, docker and ngspice versions and the exact commit. A rerun
of a failed job after the PC died mid-run can hit an already-uploaded `core-*` artifact name; that is
existing behaviour of the evidence uploads and is not changed here.

## 3. What is preserved, and what is added

Preserved unchanged: every gate command, `assert_clean_tree --gate ... --record ...`, the
`core-*-<source_sha>` evidence artifacts that `hardening_assurance` requires by name, and the
requirement that the four Python 3.12 gates resolve a **byte-identical** `pip freeze`. That requirement
is fail-closed and gets slightly more exposed here: 18 jobs on ~6 instances start over a longer window
than on hosted, so a dependency release landing inside it fails the assurance build (re-run the gates).

Added to each heavy job (the same text in each, inside the certified workflows):

* `permissions: contents: read` and `persist-credentials: false` on checkout: the PC never holds a token
  that can write to the repository.
* **Exact commit**: a step asserts `git rev-parse HEAD` equals the commit under test (`source_sha`, or
  `github.sha` in `tests.yml`) and that the tree is clean *before* any gate runs.
* **Job-scoped virtualenv** (self-hosted only): each job installs into `$RUNNER_TEMP/job-venv`, so a
  package an earlier job installed cannot satisfy this job's imports and hide a missing dependency from
  `test_every_dependency_the_tree_reaches_for_is_declared`.
* The scientific gates require `ngspice` on the PC and **fail clearly** if it is absent (GitHub-hosted
  still installs it with apt, as before).
* `benchmark` keeps its scratch file in `$RUNNER_TEMP`, not the shared `/tmp`.

`reproduce` claims "reproduces from a bare machine", so it builds with `docker build --pull --no-cache`:
no layer is reused, because a cached dependency layer would hide upstream drift that a fresh VM exposes.
It labels the image with the commit, gives the container CPU/memory/PID limits on the PC, and removes the
image afterwards.

### Per-job state and caches

| State | Handling |
| --- | --- |
| checkout, `_actions`, job scratch in `_temp`, stray files in `_work` | removed after every job and before every service start |
| Python interpreters (`_work/_tool`, `actions/setup-python`) | **removed too** (a job can write into it; a poisoned interpreter would flavour later evidence). Keep them for speed only by setting `FORGE_KEEP_TOOLCACHE=1` in the systemd drop-in, accepting that risk |
| `HOME` (dotfiles, git config, user site-packages, docker config) and `TMPDIR` | one per instance (`<instance>/_home`, `<instance>/_tmp`), emptied like the workspace |
| site-packages | a fresh venv per job |
| **pip wheel cache** (`/var/cache/forge-runner/pip`) | **kept, shared by all instances** (aged out weekly). pip still asks the index which version to install and the resolved set is recorded in `pip-freeze-*.txt`, but a cached wheel's *contents* are trusted. A hostile same-repository job could poison it. |
| Docker layers | kept for other uses, but `reproduce` does not use them; pruned when older than a week |

## 4. Threat model for a public repository

The repository is public, so **untrusted fork pull requests must never execute on the PC**.

What enforces that:

1. **The machine-side guard** (`tools/ci/runner_guard.py`, run by the job-started hook). It refuses, before
   any step runs, any job that is not: this repository, an allow-listed workflow file, and a
   `push`/`workflow_dispatch` on a branch or a `pull_request` whose event payload shows base *and* head in
   this repository, head not a fork, author OWNER/MEMBER/COLLABORATOR. Anything it cannot verify is a
   refusal. It runs under `python3 -I -S` with a fixed `PATH`, so nothing a previous job left in the
   interpreter's search path or user site can substitute for it.
2. **The repository setting** *Require approval for all outside collaborators*
   (`all_external_contributors`). It is currently `first_time_contributors`, which is too weak. The selector
   enforces it whenever `RUNNER_STATUS_TOKEN` is present; apply it with the command in section 6.
3. **Isolation of the machine**: a dedicated WSL2 distro without Windows drives or interop, a non-root user
   with no sudo, no secrets on the PC (jobs get a read-only token), per-job cleanup.

What does **not** protect the PC: `if:` conditions or `runs-on` expressions in the workflow files (a fork
controls its own copy), and the selector.

### What this design cannot do: a hostile collaborator

A job the guard **admits** runs as the runner user. That user owns the runner binaries and, because the
`reproduce` job needs Docker, is in the `docker` group, which is root-equivalent inside the distro. So
such a job can rewrite the guard, the hooks, the systemd drop-in and the runner itself, and after that
**forks are no longer refused on the machine**. The root-owned files stop accidents and stop forks; they
do not stop code that has already been admitted. Consequences, stated as requirements:

* the fork-approval setting (item 2) is a **precondition** for opting in, not advice;
* the distro must be treated as **disposable and secret-free**: rebuild it after any suspicious job and on
  a schedule (section 9);
* same-repository pull requests run arbitrary code on the PC exactly as they already do on GitHub-hosted
  runners (where they can additionally reach the workflow token). Moving gates here adds no authority over
  the certificate, which is still built and pushed by the hosted `certify` job, but it does add persistence
  that hosted VMs do not have. A poisoned pip cache or runner can carry one job's tampering into later,
  legitimate runs' evidence (section 3). That is the price of persistence; rebuilding is the mitigation.
* one OS user per instance would separate concurrent jobs but is moot while Docker is root-equivalent, so
  instances share the `forge-runner` user (each with its own `HOME`, `TMPDIR` and work directory).

## 5. Setup

Assumes Windows 11 + WSL2 (this PC: i7-14650HX, 16 cores / 24 threads, ~32 GB RAM). **Nothing below has
been executed; see section 10.**

### Part 1: the dedicated distro (Windows, PowerShell, once)

Do **not** reuse your personal Ubuntu or Docker Desktop's distro: the runner needs one with Windows drives
and interop turned off.

1. Download an Ubuntu 24.04 WSL root filesystem (`ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz` from
   `https://cloud-images.ubuntu.com/wsl/noble/current/`) and verify it against `SHA256SUMS` on that page.
2. From a checkout of this repository:

   ```powershell
   .\tools\ci\self-hosted\windows\New-ForgeRunnerDistro.ps1 `
       -RootFs D:\Downloads\ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz `
       -InstallDir D:\WSL\forge-runner -RegisterAutostart
   ```

   It imports the distro onto D: (C: is nearly full), writes `/etc/wsl.conf` (systemd on, `automount` off,
   `interop` off), terminates only that distro, and verifies that `/mnt/c` is absent and `powershell.exe`
   is not runnable.
3. Put these in `%UserProfile%\.wslconfig` (global to all WSL2 distros; the script prints it but does not
   write it), then `wsl --shutdown` when convenient:

   ```ini
   [wsl2]
   memory=24GB
   processors=20
   swap=8GB
   [experimental]
   autoMemoryReclaim=gradual
   ```

4. Windows power settings: no sleep/hibernate while you want CI to run. If the PC sleeps the runner is
   simply offline (section 2).

### Part 2: the host (inside the distro, once)

```bash
wsl -d forge-runner
# inside the distro, as root; get the repository in without Windows drives, e.g.:
apt-get update && apt-get install -y git
git clone https://github.com/sharq-labs/forge.git /root/forge && cd /root/forge
bash tools/ci/self-hosted/install-host.sh
```

It refuses to run if Windows drives or interop are visible or systemd is off. It installs git, build tools,
Python 3, **ngspice**, **docker.io**; creates user `forge-runner` (docker group, **no sudo**); installs the
guard, hooks and reset script root-owned; creates the shared cache and log directories; and enables the
weekly maintenance timer.

### Part 3: register runners (inside the distro)

Create a short-lived registration token in *Settings > Actions > Runners > New self-hosted runner*, or
`gh api -X POST repos/sharq-labs/forge/actions/runners/registration-token --jq .token`, then:

```bash
bash tools/ci/self-hosted/install-runner-instance.sh 1 <token>
bash tools/ci/self-hosted/install-runner-instance.sh 2 <token>   # a fresh token per instance
...
```

Each instance is a runner named `forge-pc-N` with labels **`self-hosted, Linux, X64, forge-pc`** (GitHub adds
the first three), a systemd service running as `forge-runner`, from the pinned runner release, refused unless
its SHA-256 matches (check `RUNNER_VERSION`/`RUNNER_SHA256` in the script against the release page). The
root-owned drop-in sets the hook variables, a per-instance `HOME` and `TMPDIR`, `PIP_CACHE_DIR`, and a
reset of the work directory before every start.

**How many instances.** One instance runs one job at a time, so N instances run N jobs in parallel. A full
recertification has 18 heavy jobs; `-n 4` pytest gates use 4 processes each, while mutation shards are
mostly serial. On this machine, start with **3 runner instances**, not 6: WSL2 is capped at 24 GB RAM and
20 processors, while Windows and Docker Desktop still need headroom. Run the smoke test and then benchmark
real FAST / SCIENTIFIC / mutation workloads while watching `free -m`, swap, CPU saturation and thermal
throttling. Scale to **4 runners only if measurements show comfortable headroom and lower wall-clock time**.
Do not assume that more runners are faster: memory pressure, xdist workers, Docker and cache/SSD contention
can make 5-6 concurrent heavy jobs slower or unstable. Keep pytest's existing `-n 4` worker counts unless
a separate measured tuning pass justifies changing them.

### Part 4: prove it, then opt in (GitHub)

1. Apply the repository setting in section 6 (a precondition, see section 4).
2. Run the **Self-hosted runner smoke test** workflow (Actions tab > *Run workflow*). It runs only on the PC
   and fails if: the hooks are not wired into **this job's** runner (it reads the Worker process's
   environment; a wiring failure means jobs are being admitted unchecked), the guard files are not
   root-owned or are directly writable, the user is root or has sudo, Windows drives or interop are visible,
   docker/ngspice/`PIP_CACHE_DIR` are missing, either Python cannot be installed, or the workspace is not the
   exact commit. `/var/log/forge-runner/hook.log` also shows the admission; note it is writable by the runner
   user, so it is a diagnostic, not evidence.
3. If the smoke test is **refused** by the guard, the runner's hook did not receive the environment the guard
   needs (section 7); every job is being refused, which is the safe direction.
4. Only then opt in:

   ```bash
   gh variable set FORGE_HEAVY_RUNNER --body self-hosted -R sharq-labs/forge
   # optional: fail fast when the PC is offline, and enforce the approval setting from CI
   gh secret set RUNNER_STATUS_TOKEN -R sharq-labs/forge
   ```

## 6. Repository settings to apply (administrator; not applied by any code here)

```bash
# public repository: nothing from an outside contributor runs until a maintainer approves it
gh api -X PUT repos/sharq-labs/forge/actions/permissions/fork-pr-contributor-approval \
   -f approval_policy=all_external_contributors
```

When approving a fork's workflow run, read its workflow-file diff first: an approved run executes the
fork's own workflow files. The PC's guard would still refuse it, but the approval is what lets it run at all
on GitHub-hosted runners. Leave *Send write tokens* / *Send secrets to workflows from fork pull requests*
off. Do not add `pull_request_target` or `workflow_run` triggers that check out pull-request code (the guard
refuses those events on the PC regardless).

## 7. What the hook relies on, and how it fails

The guard reads `GITHUB_REPOSITORY`, `GITHUB_EVENT_NAME`, `GITHUB_WORKFLOW_REF`, `GITHUB_REF`, and the event
payload at `GITHUB_EVENT_PATH`. **Whether the runner exports these to the job-started hook has not been
observed on this machine.** The guard refuses when any is missing, so that failure mode is "every job is
refused", never "a job is admitted unchecked". The other failure mode, the hook not being invoked at all, is
what the smoke test's wiring check exists to catch; re-run the smoke test after any change to the machine or
the runner. If the smoke test is refused, read `hook.log`; if the variables are absent, leave
`FORGE_HEAVY_RUNNER` unset until the guard is adapted to what the runner provides. Do not relax the guard to
make the smoke test pass.

## 8. Operating it

| Situation | What happens / what to do |
| --- | --- |
| PC off, asleep, distro stopped | heavy jobs queue; checks stay pending. Start the distro (`wsl -d forge-runner`, or log in so the scheduled task starts it). Or set `FORGE_HEAVY_RUNNER=github-hosted` to run on GitHub. |
| Reboot / power cut mid-job | the job fails or is re-queued by GitHub; on service start the instance's work directory, `HOME` and `TMPDIR` are emptied before it takes a job. Re-run the failed jobs. |
| Job refused by the guard | read `/var/log/forge-runner/hook.log`; the reason is on the line. |
| Update the guard or hooks | edit in the repository, review, then re-run `install-host.sh` on the PC. A pull request that edits the repository copy changes nothing on the PC until you do. |
| Runner update | the runner updates itself; re-check `RUNNER_VERSION`/`RUNNER_SHA256` only for new instances. |
| Disk | weekly timer prunes Docker layers >7 days and pip cache >30 days; `docker system df` and `df -h /` to check. |
| Remove an instance | `cd ~forge-runner/runners/N && ./svc.sh stop && ./svc.sh uninstall && ./config.sh remove --token <removal-token>` (as root / the runner user as appropriate). |

## 9. Keep the distro disposable

Same-repository code runs as the runner user and can persist changes in its own runner directory and, via
Docker, anywhere in the distro (section 4). Keep no credentials or personal data in it, back up nothing from
it, and rebuild it (`wsl --unregister forge-runner`, then Part 1 onward) after any suspicious job and on a
schedule you choose. That rebuild is the strongest mitigation available without ephemeral runners;
ephemeral runners would need an administration-scoped token stored on this machine, which is a worse trade
for a public repository.

## 10. Verification status

Executed in this session (on the Windows host, Python 3.14 and Git Bash; not on a runner):

* `tests/test_ci_runner_selection.py` (routing, availability, fork-approval enforcement, machine-side guard)
  and `tests/test_ci_self_hosted_scripts.py` (the reset script **run for real under bash** against a scratch
  tree, script syntax, hook and installer wiring, and workflow invariants: trust-bearing jobs stay hosted,
  heavy jobs have a read-only token/credentialless checkout/exact-commit and clean-tree assertions).
* Mutation checks with a green control first: 16 mutants of `tools/ci/` and 13 mutants of the workflows, each
  killed by a test (one survivor was found and the test tightened).
* The repository's workflow tripwires (`test_recertification_scope`, `test_certification_control_plane`,
  `test_certificate_lineage`, `test_hardening_assurance`, `test_core_guards`); all workflows parse as YAML;
  `bash -n` on every script; the PowerShell parser on the `.ps1`.
* The read-only scientific reviewer (findings and dispositions in `docs/work/PROGRESS.md`).

**NOT RUN**: any of Parts 1-4 on the PC; the hooks on a real runner (including whether the runner exports the
guard's variables to hooks, and whether the runner's `.env` could override the drop-in); `actions/setup-python`
on the WSL runner; the heavy jobs on the PC; a real recertification through it; `actionlint` (not installed);
the `RUNNER_STATUS_TOKEN` checks against the live API; the smoke workflow itself; **numerical agreement of the
pinned-digest tests on this CPU (i7-14650HX) versus GitHub's** (the first PC run of the FAST and SCIENTIFIC
tiers is that test; a failure is a platform finding to investigate, not a reason to loosen a pin). Until Part 4
passes, `FORGE_HEAVY_RUNNER` stays unset and nothing runs on the PC.
