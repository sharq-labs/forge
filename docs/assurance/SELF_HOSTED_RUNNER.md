# Self-hosted heavy CI runner (the owner's PC)

The expensive CI jobs can run on the owner's own machine instead of GitHub-hosted
runners. This page is the design, the threat model, the setup, and the operating
procedure. Nothing here changes what any gate measures, what evidence it uploads, or
what `tests-gate` / `recertification-gate` require.

## 1. What runs where

| Where | Jobs |
| --- | --- |
| **GitHub-hosted, always** | `scope`, `classify` (they decide the mode and the runner), `repo-layout`, `certificate-child`, `certify` (holds the `contents: write` token and pushes the certificate child), `verify_certificate_child`, `tests-gate`, `recertification-gate`, `branch-policy`, `select-runner` |
| **Heavy: the PC when selected** | Tests: `fast` (3.11, 3.12), `mutations`, `scientific`, `reproduce`, `benchmark`. Recertify: `fast311`, `fast312`, `scientific312`, `campaign312`, `regression312`, `formal_mutations_0-3`, `v4_mutations_0-7`, `trust_mutations`. Trust Mutations: `trust-mutations` |

Everything that can mint or push trust (certificate builder, its push, provenance
verification, the merge gates) stays on GitHub-hosted runners. The PC only runs gates
whose output is evidence the hosted `certify` job then re-checks against the source bytes.

Job names, `needs:` lists, the `if: always()` gates and the evidence artifact names are
unchanged, so `recertification_scope`, `hardening_assurance` and the branch-policy check
see the same topology (`tests/test_recertification_scope.py` pins this).

## 2. How a heavy job chooses its runner

`classify` / `scope` run `python -m tools.ci.select_heavy_runner` and expose
`heavy_runs_on` (a JSON label array). Heavy jobs use
`runs-on: ${{ fromJSON(needs.<classifier>.outputs.heavy_runs_on) }}`.

| `FORGE_HEAVY_RUNNER` (repository variable) | Event | Runs on |
| --- | --- | --- |
| unset / `github-hosted` (**default**) | any | `ubuntu-latest` |
| `self-hosted` | `push`, `workflow_dispatch` | `[self-hosted, linux, x64, forge-pc]` |
| `self-hosted` | `pull_request`, head repo = this repo, not a fork, author OWNER/MEMBER/COLLABORATOR | the PC |
| `self-hosted` | any other pull request / event | `ubuntu-latest` (coverage kept, PC untouched) |
| anything else | any | **the workflow fails**: an unknown value is never guessed |

The default is GitHub-hosted so the change that introduced this runs before any runner
exists, and so a missing PC never blocks the repository until an administrator opts in.

**This selector is routing, not the security boundary** (section 4): a fork's pull request
runs the workflow file of the fork's own merge commit and could name the PC's labels itself.

### When the PC is off, restarted or disconnected

With `self-hosted` selected the job is **never re-routed**. It waits in GitHub's queue and
the required checks stay pending (not green); GitHub fails a job that stays queued for 24
hours. To fail fast with an instruction instead, add the optional secret
`RUNNER_STATUS_TOKEN` (a fine-grained token with *Administration: read* on this repository
only). The selector then fails the run immediately with:

> no online runner carries [...]. The PC is off or its runner service is stopped. Start it, or set
> FORGE_HEAVY_RUNNER to 'github-hosted' ... Jobs are NOT re-routed automatically.

Falling back is an explicit administrator action (`gh variable set FORGE_HEAVY_RUNNER --body github-hosted`)
and is visible in every run: each heavy job uploads `runner-identity-<job>-<sha>` naming the
runner, environment, OS, kernel, CPU/RAM, Python, git, docker and ngspice versions and the exact commit.

## 3. What is preserved, and what is added

Preserved unchanged: every gate command, `assert_clean_tree --gate ... --record ...`, the
`core-*-<source_sha>` evidence artifacts (`python-*.txt`, `pip-freeze-*.txt`,
`ngspice-version.txt`, JUnit, gate JSON) that `hardening_assurance` requires by name,
and the requirement that the four Python 3.12 gates resolve a **byte-identical** `pip freeze`.

Added to each heavy job (same text in each, inside the certified workflows):

* `permissions: contents: read` and `persist-credentials: false` on checkout: the PC never
  holds a token that can write to the repository.
* **Exact commit**: a step asserts `git rev-parse HEAD` equals the commit under test
  (`source_sha`, or `github.sha` in `tests.yml`) and that the tree is clean *before* any gate runs.
* **Job-scoped virtualenv** (self-hosted only): the runner keeps its Python between jobs, so
  each job installs into `$RUNNER_TEMP/job-venv`. Without it, a package an earlier job
  installed could satisfy this job's imports and hide a missing dependency from
  `test_every_dependency_the_tree_reaches_for_is_declared`.
* The scientific gates require `ngspice` on the PC and **fail clearly** if it is absent
  (GitHub-hosted still installs it with apt, as before).

`reproduce` keeps Docker's layer cache but uses `docker build --pull`, labels the image with
the commit, gives the container CPU/memory/PID limits on the PC, and removes the image afterwards.

### Caches (safe by construction)

| Cache | Location | Why it is safe |
| --- | --- | --- |
| pip wheels | `/var/cache/forge-runner/pip` (`PIP_CACHE_DIR`, set by root-owned systemd config) | pip still asks the index for the version to install; a cached wheel is reused only if it is that exact file. Installation goes into a fresh venv every job, and the resolved set is recorded in `pip-freeze-*.txt`. Aged out weekly. |
| Python interpreters | each instance's `_work/_tool` (`actions/setup-python`) | same pinned action, same interpreter builds as GitHub-hosted |
| Docker layers | the distro's Docker | `--pull` refreshes the base tag; layers older than a week are pruned |
| Not cached | the checkout, `_actions`, `RUNNER_TEMP`, site-packages, mutation scratch trees | wiped after every job **and** whenever the service (re)starts |

Residual risk, stated plainly: the pip cache, tool cache and Docker layers are writable by
jobs that run as the runner user. Same-repository code that is malicious could poison them
for later jobs. That is inside the trust boundary of "collaborators can already run code
here" (section 4); it is why the distro is disposable (section 9).

## 4. Threat model for a public repository

The repository is public, so **untrusted fork pull requests must never execute on the PC**.

What actually enforces that:

1. **The machine-side guard** (`tools/ci/runner_guard.py`, run by the job-started hook).
   It is installed root-owned and read-only to the runner user, and wired in by a root-owned
   systemd drop-in, not by a file the runner user can edit. It refuses, before any step runs,
   any job that is not: this repository, one of the allow-listed workflow files, and a
   `push`/`workflow_dispatch` on a branch or a `pull_request` whose event payload shows base
   *and* head in this repository, head not a fork, author OWNER/MEMBER/COLLABORATOR. Anything
   it cannot verify (payload unreadable, variable unset) is a refusal.
2. **Repository setting**: *Require approval for all outside collaborators* (currently
   `first_time_contributors`, which is too weak). Apply with the command in section 6.
3. **Isolation of the machine**: a dedicated WSL2 distro without Windows drives or interop,
   a non-root user with no sudo, no secrets on the PC (jobs get a read-only token), per-job cleanup.

What does **not** protect the PC: `if:` conditions or `runs-on` expressions in the workflow
files (a fork controls its own copy), or the selector.

What this design does not do: make a **collaborator's** code safe. Same-repository pull
requests run arbitrary code on the PC, exactly as they already do on GitHub-hosted runners
(where they can additionally reach the workflow token). The PC therefore has to be treated as
disposable and secret-free (section 9). Moving gates here does not add authority over the
certificate: the certificate is still built and pushed by the hosted `certify` job.

## 5. Setup

Assumes Windows 11 + WSL2 (this PC: i7-14650HX, 16 cores / 24 threads, ~32 GB RAM).
**Nothing below has been executed; see section 10.**

### Part 1: the dedicated distro (Windows, PowerShell, once)

Do **not** reuse your personal Ubuntu or Docker Desktop's distro: the runner needs a distro
with Windows drives and interop turned off.

1. Download an Ubuntu 24.04 WSL root filesystem
   (`ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz` from `https://cloud-images.ubuntu.com/wsl/noble/current/`)
   and verify it against `SHA256SUMS` on that page.
2. From a checkout of this repository:

   ```powershell
   .\tools\ci\self-hosted\windows\New-ForgeRunnerDistro.ps1 `
       -RootFs D:\Downloads\ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz `
       -InstallDir D:\WSL\forge-runner -RegisterAutostart
   ```

   It imports the distro onto D: (C: is nearly full), writes `/etc/wsl.conf` (systemd on,
   `automount` off, `interop` off), terminates only that distro, and verifies that `/mnt/c`
   is absent and `powershell.exe` is not runnable.
3. Put these in `%UserProfile%\.wslconfig` (it is global to all WSL2 distros; the script prints
   it but does not write it), then run `wsl --shutdown` when convenient:

   ```ini
   [wsl2]
   memory=24GB
   processors=20
   swap=8GB
   [experimental]
   autoMemoryReclaim=gradual
   ```

4. Windows power settings: no sleep/hibernate while you want CI to run. If the PC sleeps the
   runner is simply offline (section 2).

### Part 2: the host (inside the distro, once)

```bash
wsl -d forge-runner
# inside the distro, as root; get the repository in without Windows drives, e.g.:
apt-get update && apt-get install -y git
git clone https://github.com/sharq-labs/forge.git /root/forge && cd /root/forge
sudo bash tools/ci/self-hosted/install-host.sh
```

It refuses to run if Windows drives or interop are visible or systemd is off. It installs
git, build tools, Python 3, **ngspice**, **docker.io**; creates user `forge-runner` (docker
group, **no sudo**); installs the guard, hooks and reset script root-owned; creates the shared
cache and log directories; and enables the weekly maintenance timer.

Docker access is root-equivalent *inside this distro*. It cannot reach Windows because the
drives and interop are off; that is the reason those two settings are not optional.

### Part 3: register runners (inside the distro)

Create a short-lived registration token in *Settings > Actions > Runners > New self-hosted
runner*, or `gh api -X POST repos/sharq-labs/forge/actions/runners/registration-token --jq .token`, then:

```bash
sudo bash tools/ci/self-hosted/install-runner-instance.sh 1 <token>
# a fresh token per instance
sudo bash tools/ci/self-hosted/install-runner-instance.sh 2 <token>
...
```

Each instance is one runner named `forge-pc-N` with labels **`self-hosted, Linux, X64, forge-pc`**
(GitHub adds the first three), installed as a systemd service running as `forge-runner`,
downloading the pinned runner release and refusing it unless its SHA-256 matches. Check the pinned
`RUNNER_VERSION` / `RUNNER_SHA256` in the script against the release page.

**How many instances.** One instance runs one job at a time, so N instances run N jobs in
parallel. A full recertification has 18 heavy jobs; `-n 4` pytest gates use 4 processes each, mutation
shards are essentially serial. Start with **6** and raise it only after watching memory
(`free -m`) and the runner-identity artifacts; with `memory=24GB` and `processors=20`, 8 is the
likely ceiling. Do not raise pytest's `-n 4`: worker counts are fixed on purpose.

### Part 4: prove it (GitHub, once, and after any machine change)

1. Run the **Self-hosted runner smoke test** workflow (Actions tab > *Run workflow*). It runs
   only on the PC and fails if the user is root or has sudo, Windows drives or interop are
   visible, docker/ngspice/`PIP_CACHE_DIR` are missing, either Python cannot be installed,
   or the workspace is not the exact commit.
2. Also read `/var/log/forge-runner/hook.log` in the distro: the run must be `admitted`. If the
   smoke test is **refused**, the runner's hook did not receive the environment the guard needs
   (see section 7) and every job is being refused, which is the safe direction.
3. Only then opt in:

   ```bash
   gh variable set FORGE_HEAVY_RUNNER --body self-hosted -R sharq-labs/forge
   ```

## 6. Repository settings to apply (administrator; not applied by any code here)

```bash
# public repository: nothing from an outside contributor runs until a maintainer approves it
gh api -X PUT repos/sharq-labs/forge/actions/permissions/fork-pr-contributor-approval \
   -f approval_policy=all_external_contributors
```

When approving a fork's workflow run, read its workflow-file diff first: an approved run
executes the fork's own workflow files. With the guard installed the PC still refuses it, but
the approval is what lets it run at all on GitHub-hosted runners.

Leave *Send write tokens* / *Send secrets to workflows from fork pull requests* off. Do not add
`pull_request_target` or `workflow_run` triggers that check out pull-request code (the guard
refuses those events on the PC regardless).

## 7. What the hook relies on, and how it fails

The guard reads `GITHUB_REPOSITORY`, `GITHUB_EVENT_NAME`, `GITHUB_WORKFLOW_REF`,
`GITHUB_REF`, and the event payload at `GITHUB_EVENT_PATH`. **Whether the runner exports these to
the job-started hook has not been observed on this machine.** The guard is written to refuse when
any is missing, so the failure mode is "every job is refused", never "a job is admitted unchecked".
If the smoke test is refused, read `hook.log`, and if the variables are absent, keep the hook
enabled and use the fallback (`FORGE_HEAVY_RUNNER` unset) until the guard is adapted to what the
runner provides. Do not relax the guard to make the smoke test pass.

## 8. Operating it

| Situation | What happens / what to do |
| --- | --- |
| PC off, asleep, distro stopped | heavy jobs queue; checks stay pending. Start the distro (`wsl -d forge-runner`, or log in so the scheduled task starts it). Or set `FORGE_HEAVY_RUNNER=github-hosted` to run on GitHub. |
| Reboot / power cut mid-job | the job fails or is re-queued by GitHub; on service start the runner's work directory is emptied before it takes a job. Re-run the failed jobs. |
| Job refused by the guard | read `/var/log/forge-runner/hook.log`; the reason is on the line. |
| Update the guard or hooks | edit in the repository, review, then re-run `install-host.sh` on the PC. A pull request that edits the repository copy changes nothing on the PC until you do. |
| Runner update | the runner updates itself; re-check `RUNNER_VERSION`/`RUNNER_SHA256` in `install-runner-instance.sh` only for new instances. |
| Disk | weekly timer prunes Docker layers >7 days and pip cache >30 days; `docker system df` and `df -h /` to check. |
| Remove an instance | `cd ~forge-runner/runners/N && sudo ./svc.sh stop && sudo ./svc.sh uninstall && ./config.sh remove --token <removal-token>`. |

## 9. Keep the distro disposable

Same-repository code runs as the runner user and can persist changes in its own runner directory.
Treat the distro as rebuildable: keep no credentials or personal data in it, back up nothing from
it, and rebuild it (`wsl --unregister forge-runner`, then Part 1 onward) after any suspicious job or
on a schedule you choose. The scheduled rebuild is the strongest single mitigation available
without ephemeral runners; ephemeral runners would need an administration-scoped token stored on
this machine, which is a worse trade for a public repository.

## 10. Verification status

Executed in this session (on the Windows host, Python 3.14, not on a runner):

* `tests/test_ci_runner_selection.py` (72 tests: routing, availability, machine-side guard) and 16
  targeted mutations of `tools/ci/`, each killed by a test.
* The workflow topology tripwires `tests/test_recertification_scope.py`,
  `tests/test_certification_control_plane.py`, `tests/test_certificate_lineage.py`,
  `tests/test_hardening_assurance.py`, `tests/test_core_guards.py`.
* All workflow files parse as YAML; `bash -n` on every shell script; PowerShell parser on the `.ps1`.

**NOT RUN**: any of Parts 1-4 on the PC; the hooks on a real runner (including whether the runner
exports the guard's variables to hooks, section 7); `actions/setup-python` on the WSL runner; the
heavy jobs on the PC; a real recertification through it; `actionlint` (not installed); the
`RUNNER_STATUS_TOKEN` availability check against the live API; **numerical agreement of the
pinned-digest tests on this CPU (i7-14650HX) versus GitHub's** (the first PC run of the FAST and
SCIENTIFIC tiers is the test of that; a failure there is a platform finding to investigate, not a
reason to loosen a pin). Until Part 4 passes, `FORGE_HEAVY_RUNNER` stays unset and nothing runs on the PC.
