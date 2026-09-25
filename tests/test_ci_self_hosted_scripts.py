"""The machine-side scripts and the workflow invariants the self-hosted runner design rests on.

The reset script is run for real (under bash) against a scratch tree. The workflow checks
read the YAML as text, the way tests/test_recertification_scope.py does, because PyYAML is
not a declared dependency of this repository.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"
SELF_HOSTED = REPO / "tools" / "ci" / "self-hosted"
BASH = shutil.which("bash")


# ------------------------------------------------------------------------- reset-instance.sh
def _reset(root: Path, work: Path | str, *, keep_tool: bool = False):
    env = {"PATH": "/usr/bin:/bin", "FORGE_RUNNERS_ROOT": root.as_posix()}
    if keep_tool:
        env["FORGE_KEEP_TOOLCACHE"] = "1"
    return subprocess.run(
        [BASH, (SELF_HOSTED / "bin" / "reset-instance.sh").as_posix(),
         work if isinstance(work, str) else work.as_posix()],
        capture_output=True, text=True, env=env,
    )


def _instance(root: Path, index: int = 1) -> Path:
    work = root / str(index) / "_work"
    for name in ("forge/forge/src", "_actions/actions/checkout", "_tool/Python/3.12.1", "_temp/job-venv", "_temp/_runner_file_commands"):
        (work / name).mkdir(parents=True)
    (work / "forge" / "forge" / "src" / "x.py").write_text("x", encoding="utf-8")
    (work / "stray.txt").write_text("stray", encoding="utf-8")
    (work / "_temp" / "runner-identity.txt").write_text("old", encoding="utf-8")
    (work / "_temp" / "_runner_file_commands" / "keep").write_text("runner bookkeeping", encoding="utf-8")
    for extra in ("_home/.local/lib", "_tmp/scratch"):
        (root / str(index) / extra).mkdir(parents=True)
    (root / str(index) / "_home" / ".gitconfig").write_text("[user]", encoding="utf-8")
    return work


@pytest.mark.skipif(BASH is None, reason="bash is required to run the machine-side scripts")
class TestResetInstance:
    def test_it_removes_what_a_job_can_leave_and_keeps_the_runners_own_bookkeeping(self, tmp_path):
        work = _instance(tmp_path)
        done = _reset(tmp_path, work)
        assert done.returncode == 0, done.stderr
        assert not (work / "forge").exists()
        assert not (work / "stray.txt").exists()
        assert not (work / "_actions").exists()
        assert not (work / "_tool").exists()                              # interpreters are wiped by default
        assert not (work / "_temp" / "job-venv").exists()
        assert not (work / "_temp" / "runner-identity.txt").exists()
        assert (work / "_temp" / "_runner_file_commands" / "keep").exists()  # underscore = the runner's
        assert list((tmp_path / "1" / "_home").iterdir()) == []
        assert list((tmp_path / "1" / "_tmp").iterdir()) == []
        assert (tmp_path / "1" / "_home").is_dir() and work.is_dir()      # the directories themselves stay

    def test_the_toolcache_can_be_kept_only_by_explicit_configuration(self, tmp_path):
        work = _instance(tmp_path)
        assert _reset(tmp_path, work, keep_tool=True).returncode == 0
        assert (work / "_tool" / "Python" / "3.12.1").exists()

    def test_it_does_not_touch_another_instance(self, tmp_path):
        one, two = _instance(tmp_path, 1), _instance(tmp_path, 2)
        assert _reset(tmp_path, one).returncode == 0
        assert (two / "forge" / "forge" / "src" / "x.py").exists()
        assert (tmp_path / "2" / "_home" / ".gitconfig").exists()

    def test_a_second_run_and_a_missing_directory_are_fine(self, tmp_path):
        work = _instance(tmp_path)
        assert _reset(tmp_path, work).returncode == 0
        assert _reset(tmp_path, work).returncode == 0
        assert _reset(tmp_path, tmp_path / "9" / "_work").returncode == 0

    @pytest.mark.parametrize(
        "relative",
        [
            "1",                     # not a work directory
            "1/_work/forge",         # a subdirectory of one
            "x/_work",               # not a numbered instance
            "1x/_work",
            "1/2/_work",             # nested
            "1/_work/../_work",      # not normalised
            "../_work",
            "1//_work",
        ],
    )
    def test_it_refuses_anything_that_is_not_exactly_a_runner_work_directory(self, tmp_path, relative):
        work = _instance(tmp_path)
        (tmp_path / "1" / "precious.txt").write_text("keep", encoding="utf-8")
        done = _reset(tmp_path, f"{tmp_path.as_posix()}/{relative}")   # a str: pathlib would normalise "//"
        assert done.returncode == 2, (done.returncode, done.stderr)
        assert "refusing" in done.stderr
        assert (tmp_path / "1" / "precious.txt").exists() and (work / "stray.txt").exists()

    def test_it_refuses_a_path_outside_the_configured_root(self, tmp_path):
        other = tmp_path / "elsewhere" / "1" / "_work"
        other.mkdir(parents=True)
        (other / "file").write_text("keep", encoding="utf-8")
        root = tmp_path / "runners"
        root.mkdir()
        assert _reset(root, other).returncode == 2
        assert (other / "file").exists()


@pytest.mark.skipif(BASH is None, reason="bash is required")
def test_every_shell_script_parses():
    for script in sorted(SELF_HOSTED.rglob("*.sh")):
        done = subprocess.run([BASH, "-n", script.as_posix()], capture_output=True, text=True)
        assert done.returncode == 0, (script.name, done.stderr)


def test_the_hook_runs_the_guard_hermetically_and_only_admits():
    text = (SELF_HOSTED / "hooks" / "job-started.sh").read_text(encoding="utf-8")
    assert "python3 -I -S" in text                       # no PYTHON* variables, no user site, no site-packages
    assert "export PATH=/usr/sbin:/usr/bin:/sbin:/bin" in text
    assert "reset-instance" not in text                  # cleanup is never done before the runner has prepared its directories


def test_the_instance_installer_wires_the_hooks_through_root_owned_configuration_and_verifies_the_download():
    text = (SELF_HOSTED / "install-runner-instance.sh").read_text(encoding="utf-8")
    assert "sha256sum -c" in text
    assert "ACTIONS_RUNNER_HOOK_JOB_STARTED=/opt/forge-runner/hooks/job-started.sh" in text
    assert "ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/opt/forge-runner/hooks/job-completed.sh" in text
    assert "/etc/systemd/system/${unit}.d/forge.conf" in text
    assert "ExecStartPre=/opt/forge-runner/bin/reset-instance.sh" in text
    assert "Environment=HOME=${dir}/_home" in text and "Environment=TMPDIR=${dir}/_tmp" in text
    assert "sudoers" not in text.replace("rm -f", "")     # the runner user is never given sudo


# ---------------------------------------------------------------- workflow invariants
def _jobs(name: str) -> dict[str, str]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)[1]
    blocks: dict[str, str] = {}
    for chunk in re.split(r"\n(?=  [A-Za-z0-9_-]+:\n)", "\n" + body):
        found = re.match(r"\n?  ([A-Za-z0-9_-]+):\n", chunk)
        if found:
            blocks[found.group(1)] = chunk
    return blocks


def _runs_on(block: str) -> str:
    found = re.search(r"\n    runs-on: ([^\n]+)\n", block)
    assert found, block[:80]
    return found.group(1).strip()


RECERTIFY_HEAVY = (
    ["fast311", "fast312", "scientific312", "campaign312", "regression312", "trust_mutations"]
    + [f"formal_mutations_{i}" for i in range(4)]
    + [f"v4_mutations_{i}" for i in range(8)]
)
#: (workflow, classifier job that emits heavy_runs_on, the heavy jobs)
HEAVY = {
    "recertify-hardened-core.yml": ("classify", RECERTIFY_HEAVY),
    "tests.yml": ("scope", ["fast", "mutations", "scientific", "reproduce", "benchmark"]),
    "trust-mutations.yml": ("select-runner", ["trust-mutations"]),
}
#: Jobs that decide, mint, push or verify trust. They never run on the personal PC.
ALWAYS_HOSTED = {
    "recertify-hardened-core.yml": ["classify", "certify", "verify_certificate_child", "recertification_gate"],
    "tests.yml": ["scope", "repo-layout", "certificate-child", "tests-gate"],
    "branch-policy.yml": ["branch-policy"],
    "trust-mutations.yml": ["select-runner"],
}


@pytest.mark.parametrize("workflow,jobs", sorted(ALWAYS_HOSTED.items()))
def test_every_job_that_mints_pushes_or_verifies_trust_stays_github_hosted(workflow, jobs):
    blocks = _jobs(workflow)
    for job in jobs:
        assert _runs_on(blocks[job]) == "ubuntu-latest", (workflow, job)
        assert "heavy_runs_on" not in blocks[job].replace("heavy_runs_on: ${{ steps.runner.outputs.heavy_runs_on }}", ""), (workflow, job)


@pytest.mark.parametrize("workflow", sorted(HEAVY))
def test_only_the_named_heavy_jobs_take_their_runner_from_the_classifier(workflow):
    classifier, heavy = HEAVY[workflow]
    blocks = _jobs(workflow)
    expected = f"${{{{ fromJSON(needs.{classifier}.outputs.heavy_runs_on) }}}}"
    using = sorted(name for name, block in blocks.items() if _runs_on(block) == expected)
    assert using == sorted(heavy)
    for name, block in blocks.items():
        assert _runs_on(block) == expected or _runs_on(block) == "ubuntu-latest", (workflow, name)


@pytest.mark.parametrize("workflow", sorted(HEAVY))
def test_every_heavy_job_has_a_read_only_token_and_a_credentialless_checkout(workflow):
    classifier, heavy = HEAVY[workflow]
    blocks = _jobs(workflow)
    for job in heavy:
        block = blocks[job]
        assert "\n    permissions:\n      contents: read\n" in block, (workflow, job)
        assert "contents: write" not in block, (workflow, job)
        assert block.count("actions/checkout@") == block.count("persist-credentials: false"), (workflow, job)
        assert f"needs: {classifier}" in block or f"      - {classifier}\n" in block or f"needs:\n      - {classifier}" in block or "needs: select-runner" in block or "needs: scope" in block


@pytest.mark.parametrize("workflow", ["recertify-hardened-core.yml", "tests.yml"])
def test_every_gate_asserts_the_exact_commit_and_a_clean_tree_before_it_runs(workflow):
    classifier, heavy = HEAVY[workflow]
    blocks = _jobs(workflow)
    for job in heavy:
        if job in ("reproduce",):
            assert 'test "$(git rev-parse HEAD)" = "${GITHUB_SHA}"' in blocks[job]
            continue
        block = blocks[job]
        assert 'git rev-parse HEAD)" != "$EXPECTED_SHA"' in block, (workflow, job)
        assert "git status --porcelain --untracked-files=all" in block, (workflow, job)
        expected = "needs.classify.outputs.source_sha" if workflow.startswith("recertify") else "github.sha"
        assert f"EXPECTED_SHA: ${{{{ {expected} }}}}" in block, (workflow, job)
        # the assertion comes before anything is installed or run
        assert block.index("EXPECTED_SHA") < block.index("pip install") if "pip install" in block else True


def test_the_self_hosted_environment_is_isolated_per_job_and_never_installs_system_packages():
    for workflow, (_, heavy) in HEAVY.items():
        blocks = _jobs(workflow)
        for job in heavy:
            block = blocks[job]
            if job in ("reproduce", "benchmark"):
                continue
            assert 'python -m venv "${RUNNER_TEMP}/job-venv"' in block, (workflow, job)
            for apt in re.findall(r"\n[^\n]*apt-get[^\n]*", block):
                assert "sudo" in apt, (workflow, job, apt)
    for job in ("scientific312",):
        assert 'RUNNER_ENVIRONMENT" = "github-hosted"' in _jobs("recertify-hardened-core.yml")[job]
    assert 'RUNNER_ENVIRONMENT" = "github-hosted"' in _jobs("tests.yml")["scientific"]


def test_the_reproducibility_image_is_built_from_scratch_and_removed_afterwards():
    block = _jobs("tests.yml")["reproduce"]
    # its claim is "a bare machine", so no reused layers: pin the build COMMAND, not a comment about it
    assert re.search(r"\n\s+docker build --pull --no-cache --label ", block)
    assert 'docker image rm -f "${IMAGE}"' in block
    assert "org.forge.commit=${GITHUB_SHA}" in block


def test_the_benchmark_job_keeps_its_scratch_in_the_job_temp_not_shared_tmp():
    block = _jobs("tests.yml")["benchmark"]
    assert "/tmp/" not in block
    assert "${RUNNER_TEMP}/split_check.json" in block


def test_the_smoke_workflow_is_manual_only_targets_only_the_personal_runner_and_checks_hook_wiring():
    text = (WORKFLOWS / "self-hosted-smoke.yml").read_text(encoding="utf-8")
    trigger = text.split("\npermissions:", 1)[0]
    assert "workflow_dispatch:" in trigger and "pull_request" not in trigger and "push:" not in trigger
    assert "runs-on: [self-hosted, linux, x64, forge-pc]" in text
    assert "contents: read" in text
    assert "ACTIONS_RUNNER_HOOK_JOB_STARTED=/opt/forge-runner/hooks/job-started.sh" in text
    assert "Runner.Worker" in text


@pytest.mark.parametrize("workflow", ["recertify-hardened-core.yml", "tests.yml"])
def test_the_classifier_selects_the_runner_from_the_repository_variable(workflow):
    classifier, _ = HEAVY[workflow]
    block = _jobs(workflow)[classifier]
    assert "FORGE_HEAVY_RUNNER: ${{ vars.FORGE_HEAVY_RUNNER }}" in block
    assert "python -m tools.ci.select_heavy_runner --check-online" in block
    assert "heavy_runs_on: ${{ steps.runner.outputs.heavy_runs_on }}" in block


# ------------------------------------------------------------------------- check-isolation.sh
# The isolation check runs for real (under sh) against a fixture tree: FORGE_ISOLATION_FIXTURE_ROOT
# makes it read proc/, run/, etc/ and mnt/ under a scratch directory instead of this machine's.
CHECK = SELF_HOSTED / "check-isolation.sh"
PS1 = SELF_HOSTED / "windows" / "New-ForgeRunnerDistro.ps1"
SH = shutil.which("sh") or BASH
PWSH = shutil.which("pwsh")
PASS = "FORGE-ISOLATION: PASS"

CANONICAL_WSL_CONF = (
    "[boot]\nsystemd=true\n\n[automount]\nenabled=false\nmountFsTab=false\n\n"
    "[interop]\nenabled=false\nappendWindowsPath=false\n\n[user]\ndefault=root\n"
)
# A WSL2 distro with automount off: its root, WSL's own tmpfs/overlay mounts, and the read-only GPU
# driver store, which is 9p (aname=drivers) but is not a drive.
CLEAN_MOUNTS = [
    "60 1 8:48 / / rw,relatime - ext4 /dev/sdd rw,discard,errors=remount-ro,data=ordered",
    "61 60 0:5 / /mnt/wsl rw,relatime shared:1 - tmpfs none rw",
    "62 60 0:32 / /usr/lib/wsl/drivers ro,nosuid,nodev,noatime - 9p none ro,dirsync,aname=drivers;fmask=222;dmask=222,mmap,access=client,msize=65536,trans=fd,rfd=7,wfd=7",
    "63 60 0:33 / /usr/lib/wsl/lib rw,relatime - overlay none rw,lowerdir=/gpu_lib_packaged:/gpu_lib_inbox,upperdir=/gpu_lib/rw/upper,workdir=/gpu_lib/rw/work",
    "64 60 0:36 / /mnt/wslg rw,relatime - tmpfs none rw",
    "65 60 0:22 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw",
    "66 60 0:40 / /run rw,nosuid,nodev shared:5 - tmpfs tmpfs rw,mode=755",
]
DRIVE_C = r"86 60 0:61 / /mnt/c rw,noatime shared:40 - 9p C:\134 rw,dirsync,aname=drvfs;path=C:\134;uid=0;gid=0;symlinkroot=/mnt/,mmap,access=client,msize=65536,trans=fd,rfd=5,wfd=5"
WSL_INTEROP = "enabled\ninterpreter /init\nflags: PF\noffset 0\nmagic 4d5a\n"


def _fixture(root: Path, *, mounts=None, stale_mnt_c=False, wsl_conf=CANONICAL_WSL_CONF,
             pid1="systemd", systemd=True, binfmt_status="enabled", handlers=None) -> Path:
    (root / "proc" / "self").mkdir(parents=True, exist_ok=True)
    if mounts is not None:
        (root / "proc" / "self" / "mountinfo").write_text("".join(m + "\n" for m in mounts), encoding="utf-8")
    fs = root / "proc" / "sys" / "fs" / "binfmt_misc"
    fs.mkdir(parents=True, exist_ok=True)
    if binfmt_status is not None:
        (fs / "status").write_text(binfmt_status + "\n", encoding="utf-8")
        (fs / "register").write_text("", encoding="utf-8")
    for name, text in (handlers or {}).items():
        (fs / name).write_text(text, encoding="utf-8")
    (root / "proc" / "1").mkdir(parents=True, exist_ok=True)
    (root / "proc" / "1" / "comm").write_text(pid1 + "\n", encoding="utf-8")
    if systemd:
        (root / "run" / "systemd" / "system").mkdir(parents=True, exist_ok=True)
    (root / "etc").mkdir(exist_ok=True)
    if wsl_conf is not None:
        (root / "etc" / "wsl.conf").write_bytes(wsl_conf.encode("utf-8"))
    (root / "mnt").mkdir(exist_ok=True)
    if stale_mnt_c:
        (root / "mnt" / "c").mkdir()
    return root


def _check(root: Path, extra_path: Path | None = None):
    path = "/usr/bin:/bin" if extra_path is None else f"{extra_path.as_posix()}:/usr/bin:/bin"
    done = subprocess.run([SH, CHECK.as_posix()], capture_output=True, text=True,
                          env={"PATH": path, "FORGE_ISOLATION_FIXTURE_ROOT": root.as_posix()})
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return done, lines


def _passes(root: Path, **kw) -> bool:
    done, lines = _check(root, **kw)
    ok = done.returncode == 0 and lines and lines[-1] == PASS
    assert ok == (done.returncode == 0), done.stdout        # the verdict line and the exit code never disagree
    return ok


@pytest.mark.skipif(SH is None, reason="a POSIX shell is required")
class TestIsolationCheck:
    def test_a_leftover_empty_mnt_c_with_nothing_mounted_is_not_a_mounted_drive(self, tmp_path):
        # The false positive that stopped New-ForgeRunnerDistro.ps1: WSL created /mnt/c on the first
        # start (before wsl.conf existed) and the directory stayed after automount was turned off.
        root = _fixture(tmp_path, mounts=CLEAN_MOUNTS, stale_mnt_c=True)
        assert (root / "mnt" / "c").is_dir()                 # what `test ! -d /mnt/c` used to fail on
        done, lines = _check(root)
        assert done.returncode == 0, done.stdout
        assert lines[0].startswith("NOTE: FIXTURE MODE")     # a fixture result never reads as the machine's
        assert lines[-1] == PASS
        assert any("mnt/c exists as a plain directory" in line for line in lines)

    def test_a_windows_drive_mounted_on_mnt_c_fails_even_though_the_directory_test_would_agree(self, tmp_path):
        root = _fixture(tmp_path, mounts=CLEAN_MOUNTS + [DRIVE_C], stale_mnt_c=True)
        done, lines = _check(root)
        assert done.returncode == 1 and lines[-1].startswith("FORGE-ISOLATION: FAIL")
        assert "FAIL: Windows drives are mounted" in done.stdout
        assert "C:\\ on /mnt/c (9p)" in done.stdout

    @pytest.mark.parametrize(
        "mount",
        [
            DRIVE_C,
            # the same drive when the mount point directory does not exist in the fixture at all
            r"87 60 0:62 / /mnt/d rw,noatime - 9p D:\134 rw,aname=drvfs;path=D:\134;uid=0;gid=0",
            # automount root moved away from /mnt: judged by the source, not the path
            r"88 60 0:63 / /win/e rw,noatime - 9p E:\134 rw,aname=drvfs;path=E:\134;uid=0",
            # WSL1-style drvfs, anywhere
            r"89 60 0:64 / /data rw,noatime - drvfs C:\134 rw,case=off",
            # the experimental virtiofs transport
            "90 60 0:65 / /mnt/f rw,noatime - virtiofs drvfsaF{0000} rw",
            # anything at all on a drive-letter mount point, whatever its type
            "91 60 0:66 / /mnt/z rw,relatime - tmpfs tmpfs rw",
        ],
    )
    def test_every_form_of_a_mounted_drive_fails(self, tmp_path, mount):
        assert not _passes(_fixture(tmp_path, mounts=CLEAN_MOUNTS + [mount]))

    @pytest.mark.parametrize(
        "mounts,expected",
        [
            (None, "cannot read the mount table"),
            ([], "the mount table"),                               # empty: nothing proves anything
            (CLEAN_MOUNTS + ["garbage without a separator"], "cannot parse"),
        ],
    )
    def test_a_mount_table_it_cannot_read_or_parse_fails_closed(self, tmp_path, mounts, expected):
        root = _fixture(tmp_path, mounts=mounts)
        done, _ = _check(root)
        assert done.returncode == 1 and expected in done.stdout, done.stdout

    @pytest.mark.parametrize(
        "handlers,ok",
        [
            ({}, True),
            ({"WSLInterop": WSL_INTEROP.replace("enabled", "disabled", 1)}, True),
            ({"python3.12": "enabled\ninterpreter /usr/bin/python3.12\nflags: \noffset 0\nmagic cb0d0d0a\n"}, True),
            ({"WSLInterop": WSL_INTEROP}, False),
            ({"WSLInterop-late": WSL_INTEROP}, False),
            ({"some-other-name": WSL_INTEROP}, False),              # a PE handler under any name
            ({"x": "enabled\ninterpreter /init\nflags: F\noffset 0\nmagic 7f454c46\n"}, False),
        ],
    )
    def test_interop_is_judged_by_the_binfmt_handler_table(self, tmp_path, handlers, ok):
        assert _passes(_fixture(tmp_path, mounts=CLEAN_MOUNTS, handlers=handlers)) is ok

    def test_an_enabled_interop_handler_fails_even_if_binfmt_misc_is_switched_off_globally(self, tmp_path):
        assert not _passes(_fixture(tmp_path, mounts=CLEAN_MOUNTS, binfmt_status="disabled",
                                    handlers={"WSLInterop": WSL_INTEROP}))

    def test_an_uninspectable_binfmt_table_fails_closed(self, tmp_path):
        done, _ = _check(_fixture(tmp_path, mounts=CLEAN_MOUNTS, binfmt_status=None))
        assert done.returncode == 1 and "whether Windows programs can be started is unknown" in done.stdout

    def test_a_windows_program_on_path_fails(self, tmp_path):
        root = _fixture(tmp_path / "root", mounts=CLEAN_MOUNTS)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        exe = bin_dir / "powershell.exe"
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        exe.chmod(0o755)
        assert _passes(root)
        assert not _passes(root, extra_path=bin_dir)

    @pytest.mark.parametrize("pid1,systemd", [("init", True), ("systemd", False), ("", True)])
    def test_systemd_must_be_pid_1(self, tmp_path, pid1, systemd):
        assert not _passes(_fixture(tmp_path, mounts=CLEAN_MOUNTS, pid1=pid1, systemd=systemd))

    @pytest.mark.parametrize(
        "conf,ok",
        [
            (CANONICAL_WSL_CONF, True),
            (CANONICAL_WSL_CONF.replace("\n", "\r\n"), True),
            ("# forge\n[boot]\n  systemd = true\n[automount]\nenabled=false\nmountFsTab=false\n"
             "[interop]\nenabled=false\nappendWindowsPath=false\n", True),
            (None, False),
            (CANONICAL_WSL_CONF.replace("[automount]\nenabled=false", "[automount]\nenabled=true"), False),
            (CANONICAL_WSL_CONF.replace("mountFsTab=false\n", ""), False),      # default: fstab is mounted
            (CANONICAL_WSL_CONF.replace("[interop]\nenabled=false\n", "[interop]\n"), False),  # default: on
            (CANONICAL_WSL_CONF.replace("appendWindowsPath=false", "appendWindowsPath=true"), False),
            (CANONICAL_WSL_CONF.replace("systemd=true", "systemd=false"), False),
            (CANONICAL_WSL_CONF.replace("[interop]\nenabled=false", "[interop]\nEnabled=false"), False),  # exact keys only
            (CANONICAL_WSL_CONF.replace("[automount]\nenabled=false", "[automount]\nenabled=false # off"), False),
        ],
    )
    def test_wsl_conf_must_keep_the_isolation_across_a_restart(self, tmp_path, conf, ok):
        assert _passes(_fixture(tmp_path, mounts=CLEAN_MOUNTS, wsl_conf=conf)) is ok


def test_no_caller_judges_a_mounted_drive_by_directory_existence_and_all_share_one_check():
    ps1 = PS1.read_text(encoding="utf-8")
    host = (SELF_HOSTED / "install-host.sh").read_text(encoding="utf-8")
    smoke = (WORKFLOWS / "self-hosted-smoke.yml").read_text(encoding="utf-8")
    for name, text in (("ps1", ps1), ("install-host", host), ("smoke", smoke)):
        assert "-d /mnt/c" not in text, name
        assert "/mnt/*/Windows" not in text, name
        assert "check-isolation.sh" in text, name
    assert "unset FORGE_ISOLATION_FIXTURE_ROOT" in host and "unset FORGE_ISOLATION_FIXTURE_ROOT" in smoke
    # fail-closed at the caller too: an exit code of 0 without the PASS verdict is a failure
    assert "'FORGE-ISOLATION: PASS'" in ps1 and '"FORGE-ISOLATION: PASS"' in smoke
    assert "if ! sh \"$here/check-isolation.sh\"; then" in host
    # the configuration the check requires is the configuration the script writes
    block = ps1.split('$wslConf = @"\n', 1)[1].split('\n"@', 1)[0]
    assert block + "\n" == CANONICAL_WSL_CONF


# ------------------------------------------------------ New-ForgeRunnerDistro.ps1, end to end
# pwsh runs the real script against a fake wsl.exe that keeps its "distros" in a state directory and
# executes what the script sends into the distro against a fixture tree. This exercises the script's
# control flow and its fail-closed verdict handling; it does NOT exercise Windows' native-argument
# quoting or a real WSL, which only a run on the PC does.
FAKE_WSL = r"""#!/usr/bin/env bash
set -u
state="$FAKE_WSL_STATE"; fix="$FAKE_WSL_FIXTURE"
printf '%s\n' "$*" >> "$state/calls.log"
case "$1" in
  --list)
    if [[ " $* " == *" --running "* ]]; then [ -e "$state/running" ] && cat "$state/distros"; exit 0; fi
    cat "$state/distros" 2>/dev/null; exit 0 ;;
  --terminate) rm -f "$state/running"; exit 0 ;;
  --import) printf '%s\n' "$2" >> "$state/distros"; exit 0 ;;
  -d)
    grep -qx -- "$2" "$state/distros" 2>/dev/null || { echo "There is no distribution with the supplied name." >&2; exit 1; }
    [ "$3 $4 $5 $6 $7" = "-u root --exec /bin/sh -c" ] || { echo "unexpected invocation: $*" >&2; exit 90; }
    touch "$state/running"
    [ -n "${FAKE_WSL_SWALLOW:-}" ] && exit 0
    payload="$(printf %s "${10}" | base64 -d)"
    if [[ "$payload" != *FORGE-ISOLATION* ]]; then payload="${payload//\/etc\/wsl.conf/$fix/etc/wsl.conf}"; fi
    boot="${8//\/run\//$fix/run/}"
    mkdir -p "$fix/run"
    exec env -i PATH=/usr/bin:/bin FORGE_ISOLATION_FIXTURE_ROOT="$fix" /bin/sh -c "$boot" "$9" "$(printf %s "$payload" | base64 -w0)" ;;
esac
echo "fake wsl.exe: unsupported $*" >&2; exit 91
"""


def _ps1(tmp_path: Path, *args: str, distros=("forge-runner",), swallow=False, **fixture):
    state, fix, fake_bin = tmp_path / "state", tmp_path / "fixture", tmp_path / "bin"
    for d in (state, fix, fake_bin):
        d.mkdir(exist_ok=True)
    (state / "distros").write_text("".join(d + "\n" for d in distros), encoding="utf-8")
    _fixture(fix, **fixture)
    wsl = fake_bin / "wsl.exe"
    wsl.write_text(FAKE_WSL, encoding="utf-8")
    wsl.chmod(0o755)
    env = {"PATH": f"{fake_bin.as_posix()}:/usr/bin:/bin", "HOME": tmp_path.as_posix(),
           "USERPROFILE": tmp_path.as_posix(), "FAKE_WSL_STATE": state.as_posix(), "FAKE_WSL_FIXTURE": fix.as_posix()}
    if swallow:
        env["FAKE_WSL_SWALLOW"] = "1"
    done = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", PS1.as_posix(), *args],
                          capture_output=True, text=True, env=env, timeout=120)
    calls = (state / "calls.log").read_text(encoding="utf-8") if (state / "calls.log").exists() else ""
    return done, calls, fix


@pytest.mark.skipif(PWSH is None or BASH is None, reason="pwsh and bash are required for the end-to-end script test")
class TestNewForgeRunnerDistroScript:
    def test_resuming_on_the_existing_distro_passes_the_previous_false_positive(self, tmp_path):
        done, calls, fix = _ps1(tmp_path, "-UseExisting", mounts=CLEAN_MOUNTS, stale_mnt_c=True)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "Isolation verified." in done.stdout and PASS in done.stdout
        assert "--import" not in calls and "--terminate forge-runner" in calls    # restarted, not recreated
        assert "already has the required configuration" in done.stdout
        assert (fix / "etc" / "wsl.conf").read_text(encoding="utf-8") == CANONICAL_WSL_CONF

    def test_resuming_rewrites_a_wrong_wsl_conf_and_verifies_after_the_restart(self, tmp_path):
        wrong = CANONICAL_WSL_CONF.replace("[automount]\nenabled=false", "[automount]\nenabled=true")
        done, calls, fix = _ps1(tmp_path, "-UseExisting", mounts=CLEAN_MOUNTS, wsl_conf=wrong)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "rewriting it" in done.stdout
        assert (fix / "etc" / "wsl.conf").read_bytes() == CANONICAL_WSL_CONF.encode()
        assert calls.index("--terminate") < calls.rindex("-d forge-runner")      # verified after the restart

    def test_a_real_mount_on_mnt_c_still_fails_the_script(self, tmp_path):
        done, _, _ = _ps1(tmp_path, "-UseExisting", mounts=CLEAN_MOUNTS + [DRIVE_C], stale_mnt_c=True)
        assert done.returncode != 0
        out = done.stdout + done.stderr
        assert "isolation check failed" in out and "Windows drives are mounted" in out
        assert "Isolation verified." not in out

    def test_live_interop_fails_the_script(self, tmp_path):
        done, _, _ = _ps1(tmp_path, "-UseExisting", mounts=CLEAN_MOUNTS, handlers={"WSLInterop": WSL_INTEROP})
        assert done.returncode != 0 and "Windows interop is live" in done.stdout + done.stderr

    def test_a_check_that_exits_0_without_a_pass_verdict_is_a_failure(self, tmp_path):
        done, _, _ = _ps1(tmp_path, "-UseExisting", mounts=CLEAN_MOUNTS, swallow=True)
        assert done.returncode != 0 and "no PASS verdict" in done.stdout + done.stderr

    def test_use_existing_refuses_a_distro_that_does_not_exist(self, tmp_path):
        done, calls, _ = _ps1(tmp_path, "-UseExisting", distros=(), mounts=CLEAN_MOUNTS)
        assert done.returncode != 0 and "No WSL distro named 'forge-runner'" in done.stdout + done.stderr
        assert "-d forge-runner" not in calls

    def test_creating_over_an_existing_distro_is_refused_and_points_at_use_existing(self, tmp_path):
        rootfs = tmp_path / "rootfs.tar.gz"
        rootfs.write_bytes(b"x")
        done, calls, _ = _ps1(tmp_path, "-RootFs", rootfs.as_posix(), "-InstallDir", (tmp_path / "inst").as_posix(),
                              mounts=CLEAN_MOUNTS)
        assert done.returncode != 0 and "-UseExisting" in done.stdout + done.stderr
        assert "--import" not in calls

    def test_a_fresh_create_imports_writes_wsl_conf_restarts_and_verifies(self, tmp_path):
        rootfs = tmp_path / "rootfs.tar.gz"
        rootfs.write_bytes(b"x")
        done, calls, fix = _ps1(tmp_path, "-RootFs", rootfs.as_posix(), "-InstallDir", (tmp_path / "inst").as_posix(),
                                distros=(), mounts=CLEAN_MOUNTS, stale_mnt_c=True, wsl_conf=None)
        assert done.returncode == 0, done.stdout + done.stderr
        assert calls.index("--import forge-runner") < calls.index("--terminate") < calls.rindex("-d forge-runner")
        assert (fix / "etc" / "wsl.conf").read_bytes() == CANONICAL_WSL_CONF.encode()
