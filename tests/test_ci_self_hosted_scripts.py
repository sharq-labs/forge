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
