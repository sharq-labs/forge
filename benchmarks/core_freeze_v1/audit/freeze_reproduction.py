"""Core Freeze V1 -- Parts 6, 7, 8, 10 and 11, reproduced from a built wheel.

    python -X utf8 benchmarks/core_freeze_v1/audit/freeze_reproduction.py <workdir> <evidence-dir>

Writes ``REPRODUCTION.json`` and ``REPRODUCTION_OUTPUT.json`` into <evidence-dir>,
OUTSIDE the repository while assurance is still running (the certificate and
freeze-manifest suites refuse a dirty tree); they are copied into
``benchmarks/core_freeze_v1/`` and committed afterwards.

WHAT THIS PROVES, AND HOW EACH PROOF COULD HAVE LIED
-----------------------------------------------------
1. The wheel is built from ``git archive HEAD`` -- committed bytes only -- with
   ``SOURCE_DATE_EPOCH`` set to the commit's own timestamp. A plain build is not
   byte-reproducible (zip entry timestamps differ between runs; measured before
   this script was written), so the artefact hash is only meaningful under a
   fixed epoch. The RECORD content digest -- the hash of every shipped file's
   own hash -- is reproducible either way and is the identity the freeze pins.
   The build runs TWICE and both digests must agree.

2. Isolation. Every wheel-side process runs ``python -S -E`` through a launcher
   that puts the install target first and asserts ``engcore.__file__`` is under
   it before anything else runs. ``-I`` is NOT enough and was the Sprint 9
   trap: it implies ``-E`` but still runs site.py, which registers this venv's
   editable hook and imports the CHECKOUT.

3. The checkout cannot satisfy a missing module. A copy of the install has one
   module deleted and is imported with the working directory set to the
   repository and ``PYTHONPATH`` pointing at ``src/`` -- the two easiest ways
   for the checkout to leak back in. The import must FAIL. A pass here would
   mean every wheel result above was quietly reading the checkout.

4. Determinism. ``reproduce.py`` prints every contractually deterministic fact
   as one canonical JSON document. It runs under several hash seeds and working
   directories, in the source checkout and in the installed wheel, and every
   output must be byte-identical.

5. The Core's own tests, run against the wheel. The install target is placed at
   ``<work>/src`` so that tests reading ``REPO / "src"`` walk the installed files
   rather than finding nothing and passing vacuously. Two tests are deselected,
   with the reason: they spawn ``sys.executable`` -- the venv interpreter WITH
   site.py -- which would import the checkout and pass without proving anything.
   Their property (fresh-process determinism) is covered by (4) under ``-S -E``.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
ROUND = ROOT / "benchmarks" / "core_freeze_v1"
PROBE = ROUND / "audit" / "reproduce.py"

SITE = [sysconfig.get_paths()["purelib"], str(ROOT / ".venv" / "Lib" / "site-packages")]

WHEEL_TESTS = (
    "tests/test_core_api_snapshot.py",
    "tests/test_core_api_serialization.py",
    "tests/test_core_api_deprecation.py",
    "tests/test_core_semantic_invariants.py",
)
#: Deselected in the wheel run ONLY, for the reason in point 5 above.
WHEEL_DESELECT = (
    "tests/test_core_api_snapshot.py::test_the_snapshot_is_byte_identical_across_fresh_processes",
    "tests/test_core_api_serialization.py::test_scientific_digests_are_identical_across_fresh_processes",
)

LAUNCHER = '''\
import os, pathlib, runpy, sys

TARGET = pathlib.Path(os.environ["FREEZE_TARGET"]).resolve()
sys.path.insert(0, str(TARGET))
for extra in os.environ.get("FREEZE_SITE", "").split(os.pathsep):
    if extra and extra not in sys.path:
        sys.path.append(extra)

import engcore

where = pathlib.Path(engcore.__file__).resolve()
if TARGET not in where.parents:
    sys.stderr.write("PROVENANCE FAILURE: engcore came from %s\\n" % where)
    raise SystemExit(97)

mode, *rest = sys.argv[1:]
if mode == "script":
    sys.argv = rest
    runpy.run_path(rest[0], run_name="__main__")
elif mode == "pytest":
    import pytest

    class _Provenance:
        """Every engcore module loaded during the run must be the wheel's."""

        def pytest_sessionfinish(self, session, exitstatus):
            strays = sorted(
                name for name, module in list(sys.modules.items())
                if name.split(".")[0] == "engcore"
                and getattr(module, "__file__", None)
                and TARGET not in pathlib.Path(module.__file__).resolve().parents
            )
            if strays:
                sys.stderr.write("PROVENANCE FAILURE: %s\\n" % strays)
                session.exitstatus = 97

    raise SystemExit(pytest.main(rest, plugins=[_Provenance()]))
elif mode == "import":
    for name in rest:
        __import__(name)
    print("IMPORTED", *rest)
else:
    raise SystemExit("unknown mode " + mode)
'''


def run(argv, **kw):
    return subprocess.run(argv, text=True, encoding="utf-8", errors="replace",
                          capture_output=True, **kw)


def commit_epoch() -> str:
    return run(["git", "log", "-1", "--format=%ct", "HEAD"], cwd=ROOT,
               check=True).stdout.strip()


def build_wheel(work: pathlib.Path, tag: str, epoch: str) -> dict:
    export, dist = work / f"export_{tag}", work / f"dist_{tag}"
    for d in (export, dist):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT,
                             capture_output=True, check=True).stdout
    tarfile.open(fileobj=io.BytesIO(archive)).extractall(export, filter="data")
    env = dict(os.environ, SOURCE_DATE_EPOCH=epoch)
    proc = run([PY, "-m", "pip", "wheel", ".", "--no-deps", "-q", "-w", str(dist)],
               cwd=export, env=env)
    if proc.returncode:
        raise SystemExit("wheel build failed:\n" + proc.stdout + proc.stderr)
    (wheel,) = list(dist.glob("*.whl"))
    with zipfile.ZipFile(wheel) as z:
        record = next(n for n in z.namelist() if n.endswith(".dist-info/RECORD"))
        lines = sorted(
            line for line in z.read(record).decode("utf-8").splitlines()
            if line and not line.split(",")[0].endswith("/RECORD")
        )
        metadata = z.read(record.replace("RECORD", "METADATA")).decode("utf-8")
        wheel_meta = z.read(record.replace("RECORD", "WHEEL")).decode("utf-8")
    field = lambda text, key: next(  # noqa: E731
        (l.split(":", 1)[1].strip() for l in text.splitlines()
         if l.startswith(key + ":")), None)
    return {
        "path": wheel,
        "filename": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "record_content_sha256": hashlib.sha256(
            "\n".join(lines).encode("utf-8")).hexdigest(),
        "record_entries": len(lines),
        "name": field(metadata, "Name"),
        "version": field(metadata, "Version"),
        "requires_python": field(metadata, "Requires-Python"),
        "wheel_tag": field(wheel_meta, "Tag"),
        "root_is_purelib": field(wheel_meta, "Root-Is-Purelib"),
    }


def install(wheel: pathlib.Path, target: pathlib.Path) -> list[str]:
    shutil.rmtree(target, ignore_errors=True)
    proc = run([PY, "-m", "pip", "install", "--no-deps", "--no-compile",
                "--target", str(target), str(wheel)])
    if proc.returncode:
        raise SystemExit("install failed:\n" + proc.stdout + proc.stderr)
    return sorted({p.relative_to(target).parts[0] for p in target.iterdir()})


def isolated(work, target, *args, cwd=None, seed="0", extra_env=None):
    launcher = work / "launcher.py"
    launcher.write_bytes(LAUNCHER.encode("utf-8"))
    env = dict(os.environ, FREEZE_TARGET=str(target),
               FREEZE_SITE=os.pathsep.join(SITE), PYTHONHASHSEED=seed)
    env.update(extra_env or {})
    return run([PY, "-S", "-E", "-X", "utf8", str(launcher), *args],
               cwd=str(cwd or work), env=env)


def main() -> int:
    work = pathlib.Path(sys.argv[1])
    evidence = pathlib.Path(sys.argv[2])
    evidence.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    head = run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True).stdout.strip()
    dirty = run(["git", "status", "--porcelain"], cwd=ROOT, check=True).stdout.strip()
    epoch = commit_epoch()
    result: dict = {"commit": head, "tree_clean": not dirty,
                    "source_date_epoch": epoch}
    print(f"commit {head}  clean={not dirty}  SOURCE_DATE_EPOCH={epoch}")

    # ---- 1. build twice ------------------------------------------------
    first = build_wheel(work, "a", epoch)
    second = build_wheel(work, "b", epoch)
    reproducible = (first["sha256"] == second["sha256"]
                    and first["record_content_sha256"] == second["record_content_sha256"])
    result["wheel"] = {k: v for k, v in first.items() if k != "path"}
    result["wheel"]["rebuild_sha256"] = second["sha256"]
    result["wheel"]["rebuild_record_content_sha256"] = second["record_content_sha256"]
    result["wheel"]["reproducible"] = reproducible
    print(f"[wheel] {first['filename']} sha256={first['sha256']}")
    print(f"[wheel] record content {first['record_content_sha256']} "
          f"({first['record_entries']} entries)  reproducible={reproducible}")

    # ---- 2. clean isolated install at <work>/src ------------------------
    target = work / "wheelroot" / "src"
    top = install(first["path"], target)
    result["install"] = {"top_level": top}
    print(f"[install] top-level: {top}")

    # ---- 3a. provenance + src alias absent ------------------------------
    # Run from the repository root with PYTHONPATH pointing at the checkout's
    # src/: the two most likely ways for the checkout to leak back in. `src` as
    # a top-level name must not resolve at all -- in the checkout it is the
    # unsupported `src.engcore` alias's parent package.
    (work / "alias_probe.py").write_bytes(
        b"import importlib.util, json, pathlib\n"
        b"import engcore\n"
        b"print(json.dumps({\n"
        b"    'engcore_file': str(pathlib.Path(engcore.__file__).resolve()),\n"
        b"    'src_top_level_importable': importlib.util.find_spec('src') is not None,\n"
        b"}))\n"
    )
    alias = isolated(work, target, "script", str(work / "alias_probe.py"),
                     cwd=ROOT, extra_env={"PYTHONPATH": str(ROOT / "src")})
    alias_out = (json.loads(alias.stdout.strip().splitlines()[-1])
                 if alias.returncode == 0 else None)
    result["provenance"] = {"exit": alias.returncode, **(alias_out or {}),
                            "stderr_tail": alias.stderr[-400:] if alias.returncode else ""}
    print(f"[provenance] {result['provenance']}")

    # ---- 3b. the checkout cannot satisfy a missing module ---------------
    broken = work / "broken" / "src"
    shutil.copytree(target, broken)
    removed = broken / "engcore" / "inference" / "split.py"
    removed.unlink()
    miss = isolated(work, broken, "import", "engcore.inference", cwd=ROOT,
                    extra_env={"PYTHONPATH": str(ROOT / "src")})
    last = next((l for l in miss.stderr.splitlines()[::-1] if "Error" in l), "")
    # The failure has to be THE deleted module, not some earlier accident: a
    # launcher provenance abort (exit 97) or an unrelated ImportError would also
    # make the import fail, and would prove nothing about the checkout.
    failed_on_the_deleted_module = (
        miss.returncode not in (0, 97)
        and last.startswith("ModuleNotFoundError")
        and "engcore.inference.split" in last
    )
    satisfied_by_checkout = not failed_on_the_deleted_module
    result["missing_module_falsification"] = {
        "removed": "engcore/inference/split.py",
        "cwd": "repository root",
        "PYTHONPATH": "repository src/",
        "import_exit": miss.returncode,
        "final_error_line": last.strip(),
        "import_failed_on_the_deleted_module": failed_on_the_deleted_module,
    }
    print(f"[falsification] {result['missing_module_falsification']}")

    # ---- 4. determinism matrix -----------------------------------------
    probe_copy = work / "reproduce.py"
    probe_copy.write_bytes(PROBE.read_bytes())
    outputs: dict[str, str] = {}
    blobs: dict[str, bytes] = {}
    matrix = []
    for seed in ("0", "1", "4242", "random"):
        matrix.append(("source", seed, ROOT))
    matrix.append(("source", "random", pathlib.Path(os.environ.get("TMPDIR", str(work)))))
    for seed in ("0", "random"):
        matrix.append(("wheel", seed, work))
        matrix.append(("wheel", seed, ROOT))
    for side, seed, cwd in matrix:
        label = f"{side}|seed={seed}|cwd={'repo' if cwd == ROOT else 'elsewhere'}"
        if side == "source":
            env = dict(os.environ, PYTHONHASHSEED=seed)
            proc = subprocess.run([PY, "-X", "utf8", str(PROBE)], cwd=str(cwd),
                                  env=env, capture_output=True)
        else:
            proc = subprocess.run(
                [PY, "-S", "-E", "-X", "utf8", str(work / "launcher.py"),
                 "script", str(probe_copy)],
                cwd=str(cwd), capture_output=True,
                env=dict(os.environ, FREEZE_TARGET=str(target),
                         FREEZE_SITE=os.pathsep.join(SITE), PYTHONHASHSEED=seed),
            )
        if proc.returncode:
            raise SystemExit(f"{label} failed:\n{proc.stderr.decode('utf-8', 'replace')}")
        blobs[label] = proc.stdout
        outputs[label] = hashlib.sha256(proc.stdout).hexdigest()
        print(f"[determinism] {label:40} {outputs[label]}")
    identical = len(set(outputs.values())) == 1
    reference = json.loads(next(iter(blobs.values())))
    result["determinism"] = {"runs": outputs, "all_identical": identical,
                             "reproduction_sha256": next(iter(outputs.values()))}
    # The canonical bytes themselves, once. Not duplicated into this summary:
    # REPRODUCTION.json names their digest, and anyone can hash the file.
    (evidence / "REPRODUCTION_OUTPUT.json").write_bytes(next(iter(blobs.values())))

    # ---- 5. the Core's own tests against the wheel ----------------------
    tests_root = work / "wheelroot"
    (tests_root / "tests").mkdir(parents=True, exist_ok=True)
    for name in WHEEL_TESTS:
        shutil.copy2(ROOT / name, tests_root / name)
    shutil.copytree(ROOT / "tests" / "api", tests_root / "tests" / "api")
    (tests_root / "pytest.ini").write_bytes(
        b"[pytest]\n# Deliberately NOT the repository's configuration: that one puts\n"
        b"# src/ and . on pythonpath, which is the checkout.\n")
    argv = ["pytest", "-q", "-p", "no:cacheprovider", "--basetemp",
            str(work / "bt"), "--rootdir", str(tests_root)]
    for item in WHEEL_DESELECT:
        argv += ["--deselect", item]
    argv += list(WHEEL_TESTS)
    proc = isolated(work, target, *argv, cwd=tests_root)
    tail = [l for l in (proc.stdout + proc.stderr).strip().splitlines() if l.strip()]
    result["wheel_tests"] = {
        "files": list(WHEEL_TESTS),
        "deselected": list(WHEEL_DESELECT),
        "deselected_because": (
            "they spawn sys.executable, the venv interpreter WITH site.py, which "
            "imports the checkout; fresh-process determinism is covered under "
            "-S -E by the determinism matrix instead"
        ),
        "exit": proc.returncode,
        "summary": tail[-1] if tail else "",
        "provenance_failure": "PROVENANCE FAILURE" in proc.stderr,
    }
    print(f"[wheel tests] exit={proc.returncode} {result['wheel_tests']['summary']}")

    api = reference["api"]
    checks = {
        "tree_clean": result["tree_clean"],
        "wheel_reproducible": reproducible,
        "engcore_from_install_target": bool(alias_out) and "wheelroot" in alias_out["engcore_file"],
        "src_alias_absent": bool(alias_out) and not alias_out["src_top_level_importable"],
        "checkout_cannot_satisfy_missing_module": not satisfied_by_checkout,
        "determinism_all_identical": identical,
        "frozen_count_194": api["frozen_count"] == 194,
        "experimental_count_11": len(api["experimental"]) == 11,
        "wheel_tests_green": proc.returncode == 0 and not result["wheel_tests"]["provenance_failure"],
    }
    result["checks"] = checks
    result["verdict"] = "REPRODUCED" if all(checks.values()) else "NOT_REPRODUCED"
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"\n{result['verdict']}  frozen digest {api['frozen_digest']}")

    (evidence / "REPRODUCTION.json").write_bytes(
        json.dumps(result, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    return 0 if result["verdict"] == "REPRODUCED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
