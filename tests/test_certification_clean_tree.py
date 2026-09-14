"""Every source gate proves its own checkout is still the commit it measured.

Finding D of the certification trust-closure round. In the parallel pipeline a
gate that writes into the repository can report success while certify starts
from a fresh checkout and never sees it. ``assert_clean_tree`` runs at the end
of each gate, and these cases make it fail once for each way a tree can move.
"""

from __future__ import annotations

import json

import pytest

from tests import certification_fixtures as fx
from tools.certification import assert_clean_tree as act


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    fx.make_repo(root)
    return root


def _paths(root):
    return {(d.status, d.path) for d in act.tree_problems(root)}


def test_a_clean_checkout_passes_and_records_its_commit(repo, tmp_path, capsys):
    record = tmp_path / "gate.json"
    assert act.main(["--root", str(repo), "--gate", "fast311", "--record", str(record)]) == 0
    written = json.loads(record.read_bytes())
    assert written["head_commit"] == fx.git(repo, "rev-parse", "HEAD")
    assert written["gate"] == "fast311" and written["clean_tree_after_gate"] is True
    assert "byte-identical" in capsys.readouterr().out


def test_a_modified_tracked_file_fails_and_is_named(repo, capsys):
    fx.write(repo, "src/engcore/scientific/record.py", "VALUE = 2\n")
    assert ("MODIFIED", "src/engcore/scientific/record.py") in _paths(repo)
    assert act.main(["--root", str(repo)]) == 1
    assert "src/engcore/scientific/record.py" in capsys.readouterr().out


def test_a_new_untracked_file_fails_and_is_named(repo, capsys):
    fx.write(repo, "src/engcore/scientific/new module.py", "X = 1\n")
    assert ("UNTRACKED", "src/engcore/scientific/new module.py") in _paths(repo)
    assert act.main(["--root", str(repo)]) == 1
    assert "new module.py" in capsys.readouterr().out


def test_a_deleted_tracked_file_fails_and_is_named(repo, capsys):
    (repo / "tests" / "mutation_guards.py").unlink()
    assert ("DELETED", "tests/mutation_guards.py") in _paths(repo)
    assert act.main(["--root", str(repo)]) == 1
    assert "tests/mutation_guards.py" in capsys.readouterr().out


def test_a_staged_rename_names_both_paths(repo):
    fx.git(repo, "mv", "README.md", "README.txt")
    paths = {path for _status, path in _paths(repo)}
    assert {"README.md", "README.txt"} <= paths


def test_a_line_ending_rewrite_git_status_hides_is_still_caught(repo):
    """With ``* text=auto eol=lf`` Git normalizes CRLF back to the indexed blob.

    ``git status`` can therefore call a CRLF rewrite clean, and every SHA-256
    byte pin in this repository breaks anyway. The byte comparison is the half
    of this check that exists for that.
    """
    target = repo / "src" / "engcore" / "scientific" / "record.py"
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    assert ("BYTES", "src/engcore/scientific/record.py") in {
        (d.status, d.path) for d in act.byte_mismatches(repo)
    }
    assert "src/engcore/scientific/record.py" in {path for _s, path in _paths(repo)}


def test_ignored_build_output_is_not_a_change(repo):
    fx.write(repo, ".gitignore", "__pycache__/\n*.egg-info/\n")
    fx.commit(repo, "ignore build output")
    fx.write(repo, "src/engcore/scientific/__pycache__/record.cpython-312.pyc", b"\x00")
    fx.write(repo, "src/crafty.egg-info/PKG-INFO", "Name: crafty\n")
    assert act.tree_problems(repo) == []


def test_the_check_never_cleans_the_evidence_it_reports(repo):
    target = fx.write(repo, "tests/mutation_guards.py", "MUTATIONS = ()\n")
    fx.write(repo, "stray.txt", "left by a gate\n")
    assert act.main(["--root", str(repo)]) == 1
    assert target.read_bytes() == b"MUTATIONS = ()\n"
    assert (repo / "stray.txt").exists()
    assert act.main(["--root", str(repo)]) == 1


def test_no_gate_record_is_written_for_a_dirty_tree(repo, tmp_path):
    fx.write(repo, "README.md", "changed\n")
    record = tmp_path / "gate.json"
    assert act.main(["--root", str(repo), "--gate", "fast311", "--record", str(record)]) == 1
    assert not record.exists()
