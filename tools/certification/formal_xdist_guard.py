"""Structured infrastructure evidence for Formal mutation attempts run under pytest-xdist.

Loaded explicitly (``-p xdist.plugin -p tools.certification.formal_xdist_guard``) only when a
Formal shard runs with more than one pytest worker. Plugin autoload stays disabled.

Why it exists: serial pytest dies with a signal exit when a test crashes the interpreter, which
the harness refuses as infrastructure. Under xdist the same crash becomes exit 1 and a synthetic
``FAILED <nodeid>`` report that the Formal rule would credit as the named guard firing. This plugin
records xdist's own structured signals on the controller -- node ready/down (with or without an
error), synthetic crash reports, internal errors, per-worker collections, per-worker interpreter
identity and UTF-8 mode, and per-process import origins -- into one JSON sentinel OUTSIDE the
worker tree. :func:`problems` is the harness side: anything but a complete, clean sentinel is an
infrastructure failure and can never earn credit.

The plugin only observes. It never selects, deselects, reorders, reschedules, retries or changes a
test, a report or an outcome.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
import sys
import tempfile

from tools.certification.mutation_startup import formal_xdist_worker_spec

SCHEMA = "forge.formal_xdist_guard/2"
OPTION = "--forge-xdist-sentinel"
_FACTS = "forge_formal_xdist_facts"
_MAX_BYTES = 1024 * 1024
#: Secondary, fail-closed check only. The structured sentinel is the authority.
CRASH_MARKERS = re.compile(r"\[gw\d+\] node down: |worker 'gw\d+' crashed while running |"
                           r"crashed and worker restarting disabled|maximum crashed workers reached")
_STATE: dict | None = None


# ---------------------------------------------------------------------------
# pytest plugin side (controller records; workers only report their own facts)
# ---------------------------------------------------------------------------
def pytest_addoption(parser):
    parser.addoption(OPTION, dest="forge_xdist_sentinel", default=None,
                     help="Forge Formal harness: write the xdist infrastructure sentinel here")


def _integer(value):
    # xdist stores --max-worker-restart as the command-line string; anything non-integral stays raw
    # and therefore cannot match the declared configuration.
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def pytest_configure(config):
    global _STATE
    if hasattr(config, "workerinput"):
        return
    _STATE = {"schema": SCHEMA, "sentinel": config.getoption("forge_xdist_sentinel"),
              "tx": list(config.getoption("tx", None) or []),
              "numprocesses": config.getoption("numprocesses", None),
              "dist": config.getoption("dist", None),
              "max_worker_restart": _integer(config.getoption("maxworkerrestart", None)),
              "ready": [], "finished": {}, "collections": {}, "events": []}


def _event(kind, **detail):
    if _STATE is not None:
        _STATE["events"].append({"kind": kind, **{k: str(v)[:500] for k, v in detail.items()}})


def pytest_testnodeready(node):
    if _STATE is not None:
        _STATE["ready"].append(node.gateway.id)


def pytest_xdist_node_collection_finished(node, ids):
    if _STATE is not None:
        digest = hashlib.sha256("\n".join(sorted(ids)).encode("utf-8", "surrogateescape")).hexdigest()
        _STATE["collections"][node.gateway.id] = [len(ids), digest]


def pytest_testnodedown(node, error):
    if _STATE is None:
        return
    if error is not None:
        _event("node_down", node=node.gateway.id, error=error)
        return
    output = getattr(node, "workeroutput", None) or {}
    _STATE["finished"][node.gateway.id] = output.get(_FACTS)


def pytest_runtest_logreport(report):
    # xdist synthesises a report with when="???" for the item a crashed worker was running.
    if _STATE is not None and report.when not in ("setup", "call", "teardown"):
        _event("crash_report", nodeid=report.nodeid, when=report.when)


def pytest_internalerror(excrepr, excinfo):
    _event("internal_error", detail=excrepr)


def _project_tops(config, root: pathlib.Path) -> set[str]:
    # Every importable name the run's own search roots provide: the rootdir, src/ and each
    # pytest ``pythonpath`` entry (e.g. tests/hybrid_uq for bare helper imports).
    bases = [root, root / "src"]
    try:
        bases.extend(pathlib.Path(str(p)) for p in config.getini("pythonpath"))
    except (ValueError, KeyError):
        pass
    tops = set()
    for base in bases:
        try:
            entries = list(base.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.suffix == ".py":
                tops.add(entry.stem)
            elif entry.is_dir() and not entry.is_symlink():
                tops.add(entry.name)
    return tops


def _facts(config, exitstatus):
    root = pathlib.Path(str(config.rootpath)).resolve()
    tops = _project_tops(config, root)
    foreign, project = [], 0
    for name, module in list(sys.modules.items()):
        if name.partition(".")[0] not in tops:
            continue
        origin = getattr(module, "__file__", None)
        if not origin:
            continue
        project += 1
        if root not in pathlib.Path(origin).resolve().parents:
            foreign.append(name)
    engcore = sys.modules.get("engcore")
    return {"pid": os.getpid(), "rootdir": str(root), "cwd": os.getcwd(), "executable": sys.executable,
            "utf8_mode": sys.flags.utf8_mode, "engcore_file": getattr(engcore, "__file__", None),
            "project_modules": project, "foreign_project_modules": sorted(foreign)[:50],
            "foreign_count": len(foreign), "exitstatus": int(exitstatus)}


def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput"):
        session.config.workeroutput[_FACTS] = _facts(session.config, exitstatus)
        return
    if _STATE is None or not _STATE["sentinel"]:
        return      # No sentinel is written; the harness refuses its absence.
    document = {key: value for key, value in _STATE.items() if key != "sentinel"}
    document.update(exitstatus=int(exitstatus), session_finished=True,
                    controller=_facts(session.config, exitstatus))
    target = pathlib.Path(_STATE["sentinel"])
    fd, name = tempfile.mkstemp(prefix=".formal-xdist-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, sort_keys=True)
        os.replace(name, target)
    finally:
        pathlib.Path(name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# harness side
# ---------------------------------------------------------------------------
def _origin_problems(label, facts, root, executable, *, worker):
    found = []
    if not isinstance(facts, dict):
        return [f"{label} reported no import facts"]
    if pathlib.Path(str(facts.get("rootdir"))).resolve() != root:
        found.append(f"{label} ran with rootdir {facts.get('rootdir')}, not the mutation worker")
    if facts.get("foreign_count") != 0:
        found.append(f"{label} imported project modules from outside the mutation worker: "
                     f"{facts.get('foreign_project_modules')}")
    origin = facts.get("engcore_file")
    if origin is not None and root not in pathlib.Path(origin).resolve().parents:
        found.append(f"{label} imported engcore from {origin}")
    if facts.get("utf8_mode") != 1:
        found.append(f"{label} did not run in UTF-8 mode (serial Formal runs -X utf8)")
    if worker and facts.get("executable") != str(executable):
        found.append(f"{label} ran {facts.get('executable')}, not the shard interpreter")
    return found


def problems(sentinel, *, workers: int, root, executable, returncode: int, output: str = "") -> list[str]:
    """Why an xdist Formal attempt is not admissible infrastructure. Empty means admissible."""
    path, root = pathlib.Path(sentinel), pathlib.Path(root).resolve()
    found: list[str] = []
    if CRASH_MARKERS.search(output or ""):
        found.append("pytest-xdist reported a worker crash or lost node")
    try:
        info = path.lstat()
    except FileNotFoundError:
        return found + ["the xdist guard sentinel is missing: the controller did not finish cleanly"]
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > _MAX_BYTES:
        return found + ["the xdist guard sentinel is not one bounded regular file"]
    try:
        document = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return found + ["the xdist guard sentinel is unreadable"]
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        return found + ["the xdist guard sentinel has an unknown schema"]
    if document.get("session_finished") is not True:
        found.append("the controller session did not finish")
    if (document.get("tx") != [formal_xdist_worker_spec(workers, executable)]
            or document.get("numprocesses") is not None
            or document.get("dist") != "loadfile" or document.get("max_worker_restart") != 0):
        found.append("the xdist configuration is not the declared Formal configuration")
    if document.get("events"):
        found.append(f"xdist infrastructure events: {document['events'][:5]}")
    ready, finished = document.get("ready") or [], document.get("finished") or {}
    if len(ready) != workers or len(set(ready)) != workers:
        found.append(f"expected {workers} distinct ready workers, saw {ready}")
    if set(finished) != set(ready):
        found.append("not every started worker finished cleanly")
    collections = document.get("collections") or {}
    if set(collections) != set(ready) or len({tuple(v) for v in collections.values()}) != 1:
        found.append("the workers did not collect one identical test universe")
    for node, facts in sorted(finished.items()):
        found.extend(_origin_problems(f"worker {node}", facts, root, executable, worker=True))
    found.extend(_origin_problems("the controller", document.get("controller"), root, executable, worker=False))
    if document.get("exitstatus") != returncode:
        found.append("the controller exit status disagrees with the process exit code")
    return found
