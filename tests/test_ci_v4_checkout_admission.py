"""BR-15 F-7: the recertification workflow's V4 shards must survive the runner's own checkout.

actions/checkout disables sparse checkout, which writes ``.git/config.worktree``; the pristine-workspace admission
(``tools/certification/mutation_workspace._check_git_seed``) refuses any worktree pointer, so every V4 shard failed in
about a second on GitHub runners (PR #140, #142). The workflow now removes that file ONLY when it holds exactly the
three sparse-checkout defaults. On POSIX the real step script runs against a checkout-shaped repository; elsewhere the
step's content is checked statically (no skip: the assurance skip admission refuses unruled skips).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

from tools.certification.mutation_workspace import WorkspaceError, _check_git_seed

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "recertify-hardened-core.yml"
STEP = "- name: Remove the sparse-checkout worktree config the checkout action leaves"


def _step_script() -> str:
    block = WORKFLOW.read_text(encoding="utf-8").split(STEP, 1)[1].split("run: |\n", 1)[1]
    lines = []
    for line in block.splitlines():
        if line.strip() and not line.startswith(" " * 10):
            break
        lines.append(line[10:])
    return "\n".join(lines)


def test_every_v4_shard_runs_the_cleanup_before_the_runner():
    text = WORKFLOW.read_text(encoding="utf-8")
    for i in range(8):
        job = text.split(f"  v4_mutations_{i}:\n", 1)[1].split("\n  v4_mutations_", 1)[0]
        assert job.index(STEP) < job.index("- name: Certified V4 false-confidence mutation shard"), i
    script = _step_script()
    assert "core.sparsecheckout=false" in script and "exit 1" in script and 'rm -- "$f"' in script


def _checkout_shaped(tmp: pathlib.Path) -> pathlib.Path:
    repo = tmp / "repo"
    repo.mkdir()
    git = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], cwd=repo, check=True)
    (repo / "f.txt").write_bytes(b"x\n")
    subprocess.run([*git, "add", "f.txt"], cwd=repo, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "c"], cwd=repo, check=True)
    subprocess.run(["git", "sparse-checkout", "disable"], cwd=repo, check=True, capture_output=True)  # as checkout does
    subprocess.run(["git", "config", "--local", "--unset-all", "extensions.worktreeConfig"], cwd=repo, capture_output=True)
    return repo


@pytest.mark.parametrize("hostile", [False, True])
def test_the_step_admits_the_checkout_and_refuses_anything_else(tmp_path, hostile):
    repo = _checkout_shaped(tmp_path)
    if not (repo / ".git" / "config.worktree").exists():           # older git: nothing written, nothing to clean
        (repo / ".git" / "config.worktree").write_bytes(b"[core]\n\tsparseCheckout = false\n\tsparseCheckoutCone = false\n"
                                                        b"[index]\n\tsparse = false\n")
    if hostile:
        (repo / ".git" / "config.worktree").write_bytes(b"[core]\n\tworktree = /elsewhere\n")
    with pytest.raises(WorkspaceError, match="external Git storage"):
        _check_git_seed(repo)                                         # the failure CI showed
    if os.name == "posix" and shutil.which("bash"):
        code = subprocess.run(["bash", "-c", _step_script()], cwd=repo, capture_output=True).returncode
        if hostile:
            assert code == 1
            with pytest.raises(WorkspaceError):
                _check_git_seed(repo)
        else:
            assert code == 0
            _check_git_seed(repo)                                     # admitted
    else:
        assert "core.sparsecheckout=false" in _step_script()
