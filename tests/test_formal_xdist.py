"""Hostile specifications: Formal attempts under pytest-xdist never turn infrastructure into credit.

Serial pytest dies with a signal exit when a test crashes the interpreter, and the harness refuses
it. Under xdist the same crash is exit 1 plus a synthetic ``FAILED <nodeid>``, which the Formal
verdict rule would credit. ``tools/certification/formal_xdist_guard.py`` turns xdist's structured
worker signals into a sentinel; anything but a complete, clean sentinel refuses the round. Under
xdist a named kill must also fail ALONE in a fresh serial process, against a control proving the
same functions pass alone unmutated; import-refusal attempts run serially as before.
"""
from __future__ import annotations

import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys

import pytest

from tools.certification import formal_xdist_guard as guard
from tools.certification import mutation_startup as startup
from tools.certification import mutation_workspace as mw

REPO = pathlib.Path(__file__).resolve().parents[1]
EXE = "/venv/bin/python"
linux = pytest.mark.skipif(sys.platform != "linux", reason="Linux child-subreaper ownership")


def _mg(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / "tests"))
    import mutation_guards as mg
    return mg


# ---------------------------------------------------------------------------
# invocation
# ---------------------------------------------------------------------------
def test_default_formal_command_is_unchanged_and_xdist_is_explicit_loadfile_without_restarts(tmp_path):
    assert startup.FORMAL_PYTEST_FLAGS == ("-X", "utf8", "-m", "pytest")
    flags = startup.formal_xdist_flags(2, tmp_path / "s.json", EXE)
    assert flags == ("-p", "xdist.plugin", "--tx", f"2*popen//python={EXE} -X utf8", "--dist", "loadfile",
                     "--max-worker-restart=0", "-p", "tools.certification.formal_xdist_guard",
                     f"--forge-xdist-sentinel={tmp_path / 's.json'}")
    assert "-n" not in flags      # bare -n workers would not get -X utf8
    assert startup.MUTATION_ENVIRONMENT["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    for bad in (0, 1, -2, True, 2.0, "2"):
        with pytest.raises(ValueError):
            startup.formal_xdist_flags(bad, tmp_path / "s.json", EXE)


def test_worker_spec_round_trips_and_refuses_unrepresentable_paths():
    # The worker launcher splits the spec on "//" and shell-splits the python= value; the
    # real-runtime specs below prove the resulting workers report the shard interpreter.
    for path in (EXE, "/opt/my venv/bin/python", "/opt/it's/python"):
        count, _, rest = startup.formal_xdist_worker_spec(2, path).partition("*")
        kind, python = rest.split("//")
        assert (count, kind) == ("2", "popen") and python.startswith("python=")
        assert shlex.split(python[len("python="):]) == [path, "-X", "utf8"]
    with pytest.raises(ValueError):
        startup.formal_xdist_worker_spec(2, "//net/share/python")


def test_pytest_workers_option_parsing(monkeypatch):
    mg = _mg(monkeypatch)
    assert mg._pytest_workers(["scratch", "G1a"]) == (1, ["scratch", "G1a"])
    assert mg._pytest_workers(["--pytest-workers", "2", "scratch"]) == (2, ["scratch"])
    assert mg._pytest_workers(["--pytest-workers=3", "scratch"]) == (3, ["scratch"])
    for bad in (["--pytest-workers", "0", "s"], ["--pytest-workers", "x", "s"], ["--pytest-workers"],
                ["--pytest-workersX", "s"], ["--pytest-workers=-1", "s"]):
        with pytest.raises(SystemExit):
            mg._pytest_workers(bad)


def test_function_nodeids_apply_the_verdict_rules_own_match(monkeypatch):
    mg = _mg(monkeypatch)
    ids = ["tests/a.py::test_guard_x[case one-2]", "tests/a.py::test_guard_x[case two]",
           "tests/b.py::TestK::test_guard_x_more", "tests/c.py::test_other[test_guard_x]",
           "tests/c.py::test_unrelated"]
    assert mg._function_nodeids(ids, "test_guard_x") == [
        "tests/a.py::test_guard_x", "tests/b.py::TestK::test_guard_x_more", "tests/c.py::test_other"]
    assert mg._function_nodeids(ids, "test_absent") == []


# ---------------------------------------------------------------------------
# the admission rule
# ---------------------------------------------------------------------------
def _facts(root, executable=EXE):
    return {"pid": 1, "rootdir": str(root), "cwd": str(root), "executable": executable, "utf8_mode": 1,
            "engcore_file": str(root / "src/engcore/__init__.py"), "project_modules": 3,
            "foreign_project_modules": [], "foreign_count": 0, "exitstatus": 1}


def _clean(root, workers=2, executable=EXE):
    nodes = [f"gw{i}" for i in range(workers)]
    return {"schema": guard.SCHEMA, "tx": [startup.formal_xdist_worker_spec(workers, executable)],
            "numprocesses": None, "dist": "loadfile", "max_worker_restart": 0, "ready": nodes,
            "finished": {n: _facts(root, executable) for n in nodes},
            "collections": {n: [5, "digest"] for n in nodes}, "events": [], "exitstatus": 1,
            "session_finished": True, "controller": dict(_facts(root, executable), engcore_file=None)}


def _write(path, document):
    path.write_text(json.dumps(document))
    return path


def test_a_clean_sentinel_is_admissible(tmp_path):
    root = tmp_path / "worker"
    root.mkdir()
    sentinel = _write(tmp_path / "s.json", _clean(root))
    assert guard.problems(sentinel, workers=2, root=root, executable=EXE, returncode=1, output="1 failed") == []


@pytest.mark.parametrize("defect", [
    "missing", "crash_report", "node_down", "internal_error", "one_ready", "unfinished", "no_facts",
    "foreign", "engcore_outside", "rootdir", "collections", "exitstatus", "schema", "dist",
    "numprocesses", "tx_other_interpreter", "tx_without_utf8", "worker_not_utf8", "worker_other_interpreter",
    "controller_foreign", "controller_missing", "not_finished", "marker_in_output", "linked", "garbage",
])
def test_every_infrastructure_defect_refuses(tmp_path, defect):
    root = tmp_path / "worker"
    root.mkdir()
    doc = _clean(root)
    output = "1 failed"
    path = tmp_path / "s.json"
    edits = {
        "crash_report": lambda: doc.update(events=[{"kind": "crash_report", "nodeid": "tests/t.py::test_guard"}]),
        "node_down": lambda: doc.update(events=[{"kind": "node_down", "node": "gw0", "error": "Not properly terminated"}]),
        "internal_error": lambda: doc.update(events=[{"kind": "internal_error", "detail": "boom"}]),
        "one_ready": lambda: doc.update(ready=["gw0"]),
        "unfinished": lambda: doc["finished"].pop("gw1"),
        "no_facts": lambda: doc["finished"].update(gw1=None),
        "foreign": lambda: doc["finished"]["gw0"].update(foreign_count=1, foreign_project_modules=["engcore.x"]),
        "engcore_outside": lambda: doc["finished"]["gw0"].update(
            engcore_file=str(tmp_path / "checkout/src/engcore/__init__.py")),
        "rootdir": lambda: doc["finished"]["gw1"].update(rootdir=str(tmp_path)),
        "collections": lambda: doc["collections"].update(gw1=[4, "other"]),
        "exitstatus": lambda: doc.update(exitstatus=0),
        "schema": lambda: doc.update(schema="forge.formal_xdist_guard/1"),
        "dist": lambda: doc.update(dist="load"),
        "numprocesses": lambda: doc.update(numprocesses=2),
        "tx_other_interpreter": lambda: doc.update(tx=[startup.formal_xdist_worker_spec(2, "/other/python")]),
        "tx_without_utf8": lambda: doc.update(tx=[f"2*popen//python={EXE}"]),
        "worker_not_utf8": lambda: doc["finished"]["gw1"].update(utf8_mode=0),
        "worker_other_interpreter": lambda: doc["finished"]["gw1"].update(executable="/usr/bin/python3"),
        "controller_foreign": lambda: doc["controller"].update(foreign_count=2),
        "controller_missing": lambda: doc.pop("controller"),
        "not_finished": lambda: doc.update(session_finished=False),
    }
    if defect in edits:
        edits[defect]()
    if defect == "marker_in_output":
        output = "..[gw1] node down: Not properly terminated\n1 failed"
    if defect == "linked":
        _write(tmp_path / "real.json", doc)
        path.symlink_to(tmp_path / "real.json")
    elif defect == "garbage":
        path.write_bytes(b"\xff{not json")
    elif defect != "missing":
        _write(path, doc)
    assert guard.problems(path, workers=2, root=root, executable=EXE, returncode=1, output=output)


# ---------------------------------------------------------------------------
# the harness consults it, and a stale sentinel has no authority
# ---------------------------------------------------------------------------
@pytest.fixture
def owned(tmp_path):
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    (source / "src/guard.py").write_text("def guard():\n    return 1\n")
    with mw.PersistentWorkspace(source, tmp_path / "scratch",
                                lambda r, d: shutil.copytree(r, d, symlinks=True)) as workspace:
        yield workspace


@pytest.mark.parametrize("sentinel_state", ["clean", "crash", "absent", "stale"])
def test_formal_run_credits_only_with_a_clean_sentinel(owned, monkeypatch, sentinel_state):
    mg = _mg(monkeypatch)
    executable = owned.startup.executable
    stale = owned.artifact_path("xdist", "formal-xdist-guard.json")
    if sentinel_state == "stale":
        _write(stale, _clean(owned.work, executable=executable))      # an earlier attempt's clean sentinel
    seen = []

    def fake(argv, **kw):
        seen.append(argv)
        path = pathlib.Path(next(a for a in argv if a.startswith(guard.OPTION)).split("=", 1)[1])
        doc = _clean(owned.work, executable=executable)
        if sentinel_state == "crash":
            doc["events"] = [{"kind": "crash_report", "nodeid": "tests/t.py::test_guard"}]
        if sentinel_state in ("clean", "crash"):
            _write(path, doc)
        return subprocess.CompletedProcess(argv, 1, _summary("FAILED tests/t.py::test_guard - boom\n"), "")

    monkeypatch.setattr(mw, "run_captured", fake)
    if sentinel_state == "clean":
        code, _tail, failed, _out = mg._run(owned.work, owned.artifacts, workspace=owned, pytest_workers=2)
        assert (code, failed) == (1, ["test_guard"])
    else:
        with pytest.raises(mw.WorkspaceError, match="infrastructure failure, no mutation credit"):
            mg._run(owned.work, owned.artifacts, workspace=owned, pytest_workers=2)
    argv = seen[0]
    assert argv[argv.index("--tx") + 1] == startup.formal_xdist_worker_spec(2, executable)
    assert "--max-worker-restart=0" in argv and "--continue-on-collection-errors" in argv
    assert [a for a in argv if a.startswith("tests/")] == list(mg.TARGETS)


def test_serial_formal_run_has_no_xdist(owned, monkeypatch):
    mg = _mg(monkeypatch)
    seen = []
    monkeypatch.setattr(mw, "run_captured", lambda argv, **kw: seen.append(argv) or
                        subprocess.CompletedProcess(argv, 0, "1 passed\n", ""))
    mg._run(owned.work, owned.artifacts, workspace=owned)
    assert not any("xdist" in a or a in ("-n", "--tx") or a.startswith(guard.OPTION) for a in seen[0])


def _summary(failed_lines: str) -> str:
    """What pytest -q prints after a failure: the FAILED lines inside the short test summary block."""
    return ("tests/t.py F\n" + "=" * 20 + " short test summary info " + "=" * 20 + "\n" + failed_lines
            + "=" * 10 + " 1 failed in 0.10s " + "=" * 10 + "\n")


@pytest.mark.parametrize("code,stdout,expected", [
    (1, _summary("FAILED tests/t.py::test_guard[a] - boom\n"), True),
    (1, _summary("FAILED tests/t.py::test_other - boom\n"), False),
    (1, "FAILED tests/t.py::test_guard[a] - boom\n", False),  # no summary block: text, not a verdict
    (0, "1 passed\n", False),
    (5, "no tests ran\n", False),
    (2, "Interrupted\n", False),
    (3, "INTERNALERROR\n", mw.WorkspaceError),
    (4, "usage\n", mw.WorkspaceError),
    (-11, "", mw.WorkspaceError),
    ("timeout", "", False),
])
def test_serial_confirmation_only_credits_a_named_failure_alone(owned, monkeypatch, code, stdout, expected):
    mg = _mg(monkeypatch)
    seen = []

    def fake(argv, **kw):
        seen.append(argv)
        if code == "timeout":
            raise subprocess.TimeoutExpired(argv, 1)
        return subprocess.CompletedProcess(argv, code, stdout, "")

    monkeypatch.setattr(mw, "run_captured", fake)
    call = lambda: mg._confirm_serially(owned.work, owned.artifacts, workspace=owned,
                                        nodeids=["tests/t.py::test_guard"], expect="test_guard")
    if expected is mw.WorkspaceError:
        with pytest.raises(mw.WorkspaceError, match="serial confirmation infrastructure"):
            call()
    else:
        assert call() is expected
    # The confirmation runs exactly the command its control ran green.
    assert seen[0] == mg._alone_argv(owned, owned.artifacts, ["tests/t.py::test_guard"])
    assert "no:cacheprovider" in seen[0] and not any(a in ("--tx", "-n") or "xdist" in a for a in seen[0])
    seen.clear()
    assert mg._confirm_serially(owned.work, owned.artifacts, workspace=owned, nodeids=[], expect="x") is False
    assert seen == []


def test_confirmation_needs_the_pristine_tree_plus_exactly_the_declared_edit(owned, monkeypatch):
    mg = _mg(monkeypatch)
    seen = []
    monkeypatch.setattr(mw, "run_captured", lambda argv, **kw: seen.append(argv) or
                        subprocess.CompletedProcess(argv, 1, _summary("FAILED tests/t.py::test_guard - x\n"), ""))
    confirm = lambda **kw: mg._confirm_serially(owned.work, owned.artifacts, workspace=owned,
                                                nodeids=["tests/t.py::test_guard"], expect="test_guard", **kw)
    (owned.work / "src/guard.py").write_text("def guard():\n    return 0\n")      # the declared edit
    mutated = {"src/guard.py": mw.snapshot(owned.work)["src/guard.py"]}
    (owned.work / ".pytest_cache").mkdir()
    (owned.work / ".pytest_cache/v").write_text("{}")                          # ignored by alone runs
    assert confirm(mutated=mutated) is True
    assert confirm() is False                                                   # an undeclared edit
    (owned.work / "src/guard.py").write_text("def guard():\n    return 7\n")      # rewritten after the edit
    assert confirm(mutated=mutated) is False
    (owned.work / "src/guard.py").write_text("def guard():\n    return 0\n")
    (owned.work / "stray.txt").write_text("left by the xdist run")
    assert confirm(mutated=mutated) is False
    assert len(seen) == 1                                                       # refused before running


def test_confirmation_reads_the_name_from_the_nodeid_not_the_message(owned, monkeypatch):
    mg = _mg(monkeypatch)
    out = _summary("FAILED tests/t.py::test_other[x] - AssertionError: see tests/t.py::test_guard\n")
    monkeypatch.setattr(mw, "run_captured", lambda argv, **kw: subprocess.CompletedProcess(argv, 1, out, ""))
    assert mg._confirm_serially(owned.work, owned.artifacts, workspace=owned,
                                nodeids=["tests/t.py::test_other"], expect="test_guard") is False


def test_named_alone_control_refuses_a_copy_changed_between_its_runs(owned, monkeypatch):
    mg = _mg(monkeypatch)
    collected = "tests/a.py::test_guard_x\ntests/b.py::test_guard_y\n"

    def fake(argv, **kw):
        if "--collect-only" in argv:
            return subprocess.CompletedProcess(argv, 0, collected, "")
        (owned.work / "stray.txt").write_text("written by a named guard")
        return subprocess.CompletedProcess(argv, 0, "1 passed\n", "")

    monkeypatch.setattr(mw, "run_captured", fake)
    with pytest.raises(SystemExit, match="changed the unmutated copy"):
        mg._named_alone_control(owned.artifacts, workspace=owned, expects=["test_guard_x", "test_guard_y"])


@pytest.mark.parametrize("alone_code", [0, 1])
def test_named_alone_control_selects_by_the_rule_and_voids_a_failing_guard(owned, monkeypatch, alone_code):
    mg = _mg(monkeypatch)
    collected = "tests/a.py::test_guard_x[p]\ntests/a.py::test_ok\ntests/b.py::TestK::test_guard_y\n\n3 tests collected\n"
    seen = []

    def fake(argv, **kw):
        seen.append(argv)
        if "--collect-only" in argv:
            return subprocess.CompletedProcess(argv, 0, collected, "")
        return subprocess.CompletedProcess(argv, alone_code, "1 failed\n" if alone_code else "2 passed\n", "")

    monkeypatch.setattr(mw, "run_captured", fake)
    call = lambda: mg._named_alone_control(owned.artifacts, workspace=owned,
                                           expects=["test_guard_x", "test_guard_y", "test_absent"])
    if alone_code:
        with pytest.raises(SystemExit, match="fails alone"):
            call()
        assert len(seen) == 2                                # stops at the first set that fails alone
    else:
        assert call() == {"test_guard_x": ["tests/a.py::test_guard_x"],
                          "test_guard_y": ["tests/b.py::TestK::test_guard_y"], "test_absent": []}
        # One run per set, each EXACTLY the command its confirmation will use (no union proof).
        assert seen[1:] == [mg._alone_argv(owned, owned.artifacts, ["tests/a.py::test_guard_x"]),
                            mg._alone_argv(owned, owned.artifacts, ["tests/b.py::TestK::test_guard_y"])]
    assert "tests/a.py::test_ok" not in seen[1] and "no:cacheprovider" in seen[1] and "--tx" not in seen[1]
    assert mw.snapshot(owned.work) == owned.baseline       # its own attempt restored the copy


# ---------------------------------------------------------------------------
# main(): xdist only where asked, confirmation, serial import refusals
# ---------------------------------------------------------------------------
@pytest.fixture
def source_tree(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src/guard.py").write_text("def guard():\n    return 1\n")
    return root


def _synthetic_main(mg, monkeypatch, source_tree, calls, confirm, expect="test_guard"):
    monkeypatch.setattr(mg, "__file__", str(source_tree / "tests/mutation_guards.py"))
    monkeypatch.setattr(mg, "_self_test", lambda: None)
    monkeypatch.setattr(mg, "_validate_declarations", lambda: None)
    monkeypatch.setattr(mg, "_copy_tree", lambda r, d: shutil.copytree(r, d, symlinks=True))
    monkeypatch.setattr(mg, "MUTATIONS", [("ONE", "src/guard.py", "return 1", "return 0", "synthetic")])
    monkeypatch.setattr(mg, "EVIDENCE", {"ONE": ("synthetic", expect)})
    refusal = "E   engcore.domains.x: refused at import\n"

    def fake_run(work, scratch, *, telemetry=None, workspace=None, **kwargs):
        calls.append(kwargs)
        text = (work / "src/guard.py").read_text()
        if "return 1" in text:
            return 0, "control", [], ""
        return 1, "mutant", ["test_guard"], "FAILED tests/t.py::test_guard - boom\n" + refusal

    monkeypatch.setattr(mg, "_run", fake_run)
    monkeypatch.setattr(mg, "_named_alone_control",
                        lambda scratch, *, workspace, expects: calls.append(("named", sorted(expects)))
                        or {e: ["tests/t.py::test_guard"] for e in expects})
    monkeypatch.setattr(mg, "_confirm_serially",
                        lambda *a, nodeids, **k: calls.append(("confirm", nodeids)) or confirm)


def test_main_threads_workers_and_confirms_only_under_xdist(source_tree, tmp_path, monkeypatch, capsys):
    mg = _mg(monkeypatch)
    calls = []
    _synthetic_main(mg, monkeypatch, source_tree, calls, confirm=True)
    assert mg.main([str(tmp_path / "serial"), "ONE"]) == 0
    assert calls == [{}, {}]                         # default call shape unchanged, no confirmation
    calls.clear()
    assert mg.main(["--pytest-workers", "2", str(tmp_path / "xdist"), "ONE"]) == 0
    assert calls == [{"pytest_workers": 2}, ("named", ["test_guard"]), {"pytest_workers": 2},
                     ("confirm", ["tests/t.py::test_guard"])]
    text = capsys.readouterr().out
    assert "FORMAL PYTEST WORKERS 2" in text and "1/1 mutations were killed" in text


def test_an_unconfirmed_xdist_kill_is_not_credit(source_tree, tmp_path, monkeypatch, capsys):
    from tools.certification import mutation_population as mp
    mg = _mg(monkeypatch)
    _synthetic_main(mg, monkeypatch, source_tree, [], confirm=False)
    assert mg.main(["--pytest-workers", "2", str(tmp_path / "xdist"), "ONE"]) == 1
    text = capsys.readouterr().out
    assert "RED (NOT CONFIRMED SERIALLY)" in text and "0/1 mutations were killed" in text
    assert mp.parse_log(text, mp.Population(("ONE",))).killed == ()


def test_import_refusal_attempts_stay_serial_with_a_serial_control(source_tree, tmp_path, monkeypatch, capsys):
    mg = _mg(monkeypatch)
    calls = []
    _synthetic_main(mg, monkeypatch, source_tree, calls, confirm=False, expect=mg.REFUSED_AT_IMPORT)
    assert mg.main(["--pytest-workers", "2", str(tmp_path / "xdist"), "ONE"]) == 0
    # xdist control, historical serial control, no named guards, serial attempt, no confirmation.
    assert calls == [{"pytest_workers": 2}, {}, ("named", []), {}]
    assert "RED (refused at import)" in capsys.readouterr().out


def test_main_refuses_tools_mutations_under_xdist(source_tree, tmp_path, monkeypatch):
    mg = _mg(monkeypatch)
    _synthetic_main(mg, monkeypatch, source_tree, [], confirm=True)
    monkeypatch.setattr(mg, "MUTATIONS", [("TOOL", "tools/certification/formal_xdist_guard.py", "a", "b", "x")])
    monkeypatch.setattr(mg, "EVIDENCE", {"TOOL": ("synthetic", "test_guard")})
    with pytest.raises(SystemExit, match="cannot run mutations of tools/"):
        mg.main(["--pytest-workers", "2", str(tmp_path / "tools"), "TOOL"])


def test_transcript_records_ignore_xdist_noise():
    from tools.certification import mutation_population as mp
    population = mp.Population(("G1a", "G1d"))
    plain = ("CONTROL GREEN                unmutated copy, 90s -- a red result below is the mutation's doing\n"
             "                           1139 passed, 1 skipped in 88.0s\n\n"
             "G1a   RED                  synthetic\n"
             "                           15 failed, 1124 passed in 88.0s\n"
             "G1d   RED (refused at import) synthetic\n"
             "                           23 failed, 615 passed, 14 errors in 77.0s\n\n"
             "2/2 mutations were killed by the guard they name.\n")
    noisy = ("FORMAL PYTEST WORKERS 2 -- pytest-xdist --dist loadfile; a worker crash or lost node is an "
             "infrastructure failure, never a kill\n"
             "CONTROL GREEN                named guards pass alone: 3 test function(s), 0 name(s) with none\n"
             + plain.replace("14 errors", "56 errors")
             .replace("15 failed, 1124 passed", "[gw1] node down: Not properly terminated"))
    one, two = mp.parse_log(plain, population), mp.parse_log(noisy, population)
    assert (one.verdicts, one.tally, one.control_green, one.unknown_ids) == \
        (two.verdicts, two.tally, two.control_green, two.unknown_ids)
    assert one.killed == ("G1a", "G1d")


# ---------------------------------------------------------------------------
# real xdist, real crashes: a fresh dedicated interpreter owns each run
# ---------------------------------------------------------------------------
DRIVER = r'''
import json, pathlib, shutil, sys
repo, source, scratch, mode = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]), sys.argv[4]
expects = sys.argv[5].split(",")
sys.path[:0] = [str(repo / "tests"), str(repo)]
import mutation_guards as mg
from tools.certification import mutation_workspace as mw
from tools.certification.mutation_startup import FORMAL_PYTEST_FLAGS
mg.TARGETS = ("tests/test_alpha.py", "tests/test_beta.py")
with mw.PersistentWorkspace(source, scratch, lambda r, d: shutil.copytree(r, d, symlinks=True)) as ws:
    try:
        named = {} if mode == "plain" else mg._named_alone_control(ws.artifacts, workspace=ws, expects=expects)
        with ws.attempt(mutation_id="SPEC") as work:
            (work / "MUTANT").write_text("applied")          # the scenario's "mutation"
            mutated = {"MUTANT": mw.snapshot(work)["MUTANT"]}
            if mode == "plain":
                done = mw.run_captured([ws.startup.executable, *FORMAL_PYTEST_FLAGS, *mg.TARGETS, "-q",
                                        "-p", "xdist.plugin", "-n", "2", "--dist", "loadfile",
                                        "--max-worker-restart=0"], cwd=work, timeout=300,
                                       inherited=ws.startup.environment)
                failed = mg.failed_test_names(done.stdout)
                result = {"outcome": "PLAIN", "code": done.returncode, "failed": failed}
            else:
                code, tail, failed, out = mg._run(work, ws.artifacts, workspace=ws, pytest_workers=2)
                confirmed = mg._confirm_serially(work, ws.artifacts, workspace=ws,
                                                 nodeids=named["test_guard_named"], expect="test_guard_named",
                                                 mutated=mutated) if code == 1 else None
                result = {"outcome": "ADMITTED", "code": code, "failed": failed, "confirmed": confirmed}
    except mw.WorkspaceError as exc:
        result = {"outcome": "REFUSED", "error": str(exc)}
    except SystemExit as exc:
        result = {"outcome": "VOID", "error": str(exc)}
print(json.dumps(result))
'''

_MUTANT = "import os, pathlib\nMUTANT = pathlib.Path('MUTANT').exists()\n"
SCENARIOS = {
    "named_failure": _MUTANT + "\ndef test_guard_named():\n    assert not MUTANT\n\ndef test_ok():\n    pass\n",
    "fails_only_under_xdist": _MUTANT + ("\ndef test_guard_named():\n"
                                         "    assert not (MUTANT and 'PYTEST_XDIST_WORKER' in os.environ)\n"),
    "crash_in_named_guard": _MUTANT + ("import signal\n\ndef test_guard_named():\n"
                                       "    if MUTANT:\n        os.kill(os.getpid(), signal.SIGSEGV)\n"),
    "worker_lost_before_target": _MUTANT + ("import signal\nif MUTANT and os.environ.get('PYTEST_XDIST_WORKER') == 'gw0':\n"
                                            "    os.kill(os.getpid(), signal.SIGKILL)\n\n"
                                            "def test_guard_named():\n    assert not MUTANT\n"),
    "incomplete_worker_result": _MUTANT + "\ndef test_guard_named():\n    if MUTANT:\n        os._exit(0)\n",
    "workers_collect_different_tests": _MUTANT + ("import pytest\n\n@pytest.mark.parametrize('w', "
                                                  "[os.environ.get('PYTEST_XDIST_WORKER', 'x') if MUTANT else 'x'])\n"
                                                  "def test_guard_named(w):\n    assert not MUTANT\n"),
    "foreign_project_import": _MUTANT + "import leakpkg\n\ndef test_guard_named():\n    assert not MUTANT\n",
    "foreign_via_pythonpath_root": _MUTANT + "import leakhelper\n\ndef test_guard_named():\n    assert not MUTANT\n",
    "worker_internal_error": _MUTANT + "\ndef test_guard_named():\n    assert not MUTANT\n",
    # A named guard that only passes after another test set state up: it fails ALONE without
    # any mutation, so it can never confirm a kill (the per-set named-alone control voids the round).
    "named_guard_needs_another_test": ("import registry\n\ndef test_a_setup():\n    registry.READY = True\n\n"
                                       "def test_guard_named():\n    assert registry.READY\n"),
    # Two named guards where B only passes after A: one union run would be green, but B alone
    # fails with no mutation, so the per-set control must void the round.
    "second_guard_needs_the_first": ("import registry\n\ndef test_guard_a():\n    registry.READY = True\n\n"
                                     "def test_guard_named():\n    assert registry.READY\n"),
    # A target that writes into the worker: a confirmation must not run on that leftover tree.
    "target_writes_into_worker": _MUTANT + ("\ndef test_guard_named():\n    assert not MUTANT\n\n"
                                            "def test_writer():\n    if MUTANT:\n"
                                            "        pathlib.Path('stray.txt').write_text('x')\n"),
}


def _drive(tmp_path, scenario, mode="guarded", expects=("test_guard_named",)):
    source = tmp_path / "source"
    for package in ("tools", "tools/certification"):
        (source / package).mkdir(parents=True, exist_ok=True)
        (source / package / "__init__.py").write_text("")
    for module in ("formal_xdist_guard.py", "mutation_startup.py"):
        shutil.copy2(REPO / "tools/certification" / module, source / "tools/certification" / module)
    ini = "[tool.pytest.ini_options]\n"                     # rootdir = worker, as in production
    (source / "tests").mkdir()
    (source / "tests/test_alpha.py").write_text(SCENARIOS[scenario])
    (source / "tests/test_beta.py").write_text("def test_beta():\n    pass\n")
    outside = tmp_path / "outside"
    leak = "import pathlib, sys\nif pathlib.Path('MUTANT').exists():\n    sys.path.insert(0, {!r})\n"
    if scenario == "foreign_project_import":
        (source / "leakpkg").mkdir()
        (source / "leakpkg/__init__.py").write_text("WHERE = 'worker'\n")
        (outside / "leakpkg").mkdir(parents=True)
        (outside / "leakpkg/__init__.py").write_text("WHERE = 'outside'\n")
        (source / "tests/conftest.py").write_text(leak.format(str(outside)))
    if scenario == "foreign_via_pythonpath_root":
        ini += 'pythonpath = ["helpers"]\n'
        (source / "helpers").mkdir()
        (source / "helpers/leakhelper.py").write_text("WHERE = 'worker'\n")
        outside.mkdir()
        (outside / "leakhelper.py").write_text("WHERE = 'outside'\n")
        (source / "tests/conftest.py").write_text(leak.format(str(outside)))
    if scenario in ("named_guard_needs_another_test", "second_guard_needs_the_first"):
        (source / "tests/registry.py").write_text("READY = False\n")
        ini += 'pythonpath = ["tests"]\n'
    if scenario == "worker_internal_error":
        (source / "tests/conftest.py").write_text(
            "import os, pathlib\n\ndef pytest_runtest_logreport(report):\n"
            "    if pathlib.Path('MUTANT').exists() and os.environ.get('PYTEST_XDIST_WORKER'):\n"
            "        raise RuntimeError('worker hook failure')\n")
    (source / "pyproject.toml").write_text(ini)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "PYTHON"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    done = subprocess.run([sys.executable, "-c", DRIVER, str(REPO), str(source), str(tmp_path / "scratch"), mode,
                           ",".join(expects)], cwd=REPO, env=env, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@linux
def test_plain_xdist_would_credit_a_crash_so_the_guard_is_required(tmp_path):
    # Tripwire: if xdist ever stops converting a crash into FAILED, re-review this design.
    result = _drive(tmp_path, "crash_in_named_guard", mode="plain")
    assert result["code"] == 1 and "test_guard_named" in result["failed"]


@linux
def test_a_real_named_failure_under_xdist_is_admitted_and_confirmed(tmp_path):
    # Admission also proves every worker ran the shard interpreter in UTF-8 mode inside the worker tree.
    result = _drive(tmp_path, "named_failure")
    assert result == {"outcome": "ADMITTED", "code": 1, "failed": ["test_guard_named"], "confirmed": True}


@linux
@pytest.mark.parametrize("scenario", ["fails_only_under_xdist", "target_writes_into_worker"])
def test_a_kill_that_is_not_the_mutation_alone_is_never_confirmed(tmp_path, scenario):
    result = _drive(tmp_path, scenario)
    assert result == {"outcome": "ADMITTED", "code": 1, "failed": ["test_guard_named"], "confirmed": False}


@linux
@pytest.mark.parametrize("scenario,expects", [
    ("named_guard_needs_another_test", ("test_guard_named",)),
    # The union [test_guard_a, test_guard_named] would pass in one process; the per-set run does not.
    ("second_guard_needs_the_first", ("test_guard_a", "test_guard_named")),
])
def test_a_named_guard_that_fails_alone_unmutated_voids_the_round(tmp_path, scenario, expects):
    result = _drive(tmp_path, scenario, expects=expects)
    assert result["outcome"] == "VOID" and "fails alone" in result["error"], result


@linux
@pytest.mark.parametrize("scenario,reasons", [
    ("crash_in_named_guard", ("infrastructure events",)),
    # The lost worker never finishes collection, so no test runs: pytest exits 5 and the
    # pre-existing exit-code rule refuses before the guard is even consulted.
    ("worker_lost_before_target", ("pytest infrastructure exit 5",)),
    ("incomplete_worker_result", ("infrastructure events",)),
    ("workers_collect_different_tests", ("one identical test universe",)),
    ("foreign_project_import", ("from outside the mutation worker",)),
    ("foreign_via_pythonpath_root", ("from outside the mutation worker",)),
    ("worker_internal_error", ("pytest infrastructure exit 3", "infrastructure events")),
])
def test_real_xdist_infrastructure_failure_never_earns_credit(tmp_path, scenario, reasons):
    result = _drive(tmp_path, scenario)
    assert result["outcome"] == "REFUSED", result
    # Refused for ITS reason, not because some unrelated check refuses everything.
    assert any(reason in result["error"] for reason in reasons), result
    assert "configuration is not the declared" not in result["error"], result


@pytest.mark.parametrize("line, name", [
    ("FAILED tests/test_alpha.py::test_guard_named", "test_guard_named"),
    ("FAILED tests/test_alpha.py::test_guard_named - assert False", "test_guard_named"),
    # an xdist crash report names a nodeid inside its message, cut to the terminal width
    ("FAILED tests/test_alpha.py::test_guard_named - [gw0] node down: Not properly terminated "
     "tests/test_alpha.py::test_guard_na...", "test_guard_named"),
    ("FAILED tests/test_alpha.py::test_other - AssertionError: see tests/test_alpha.py::test_guard_named",
     "test_other"),
    ("FAILED tests/test_alpha.py::TestX::test_p[a b] - x", "test_p[a b]"),
])
def test_a_failure_is_attributed_to_its_own_nodeid_never_to_one_its_message_names(monkeypatch, line, name):
    out = "noise\n" + SUMMARY + line + "\n" + "=" * 10 + " 1 failed in 0.1s " + "=" * 10 + "\n"
    assert _mg(monkeypatch).failed_test_names(out) == [name]


SUMMARY = "=" * 20 + " short test summary info " + "=" * 20 + "\n"


def test_a_failed_line_outside_the_summary_block_is_never_credited(monkeypatch):
    """Review of 313bbf1e: captured output can print a FAILED line naming any guard."""
    mg = _mg(monkeypatch)
    out = ("tests/a.py F\n---- Captured stdout call ----\nFAILED tests/b.py::test_guard_named\n"
           + SUMMARY + "FAILED tests/a.py::test_other - x\n" + "=" * 10 + " 1 failed in 0.1s " + "=" * 10 + "\n"
           + "FAILED tests/c.py::test_guard_named\n")
    assert mg.failed_test_names(out) == ["test_other"]
    assert mg.failed_test_names("FAILED tests/b.py::test_guard_named\n") == []  # no summary block: no credit