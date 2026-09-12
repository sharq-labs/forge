"""Parts Q and R: does the installed wheel expose the same frozen API.

The question this answers cannot be answered from the repository. A snapshot
taken in a checkout describes the checkout; to learn what a CONSUMER gets, the
snapshot has to be taken from a process that has the wheel and nothing else.

THE TRAP, carried over from Sprint 9 and re-proved here
--------------------------------------------------------
``python -I`` implies ``-E``, so it ignores PYTHONPATH -- and it does NOT skip
site-packages, where this venv's editable hook for the checkout lives. Run that
way, ``import engcore`` resolves to the CHECKOUT and every assertion passes
while proving nothing.

So: ``-S -E``, with the install target inserted by an explicit launcher and
site-packages appended after it for the runtime dependencies. ``-S`` means
``site.py`` never runs, so the editable ``.pth`` hook is never registered;
appending a directory does not process its ``.pth`` files. And the launcher
ASSERTS where ``engcore`` came from before it does anything else.

    python -X utf8 benchmarks/core_api_stability/audit/wheel_parity.py <workdir>
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import sysconfig

ROOT = pathlib.Path(__file__).resolve().parents[3]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")


def sh(argv, **kw):
    print("$", " ".join(str(a) for a in argv), flush=True)
    return subprocess.run(argv, check=False, text=True, encoding="utf-8",
                          errors="replace", **kw)


def build_and_install(work: pathlib.Path) -> tuple[pathlib.Path, list[str]]:
    export, dist, install = work / "export", work / "dist", work / "install"
    for directory in (export, dist, install):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)

    archive = work / "tree.tar"
    if sh(["git", "archive", "--format=tar", "-o", str(archive), "HEAD"],
          cwd=ROOT).returncode:
        raise SystemExit("git archive failed")
    if sh(["tar", "-xf", str(archive), "-C", str(export)]).returncode:
        raise SystemExit("tar failed")

    if sh([PY, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(dist)],
          cwd=export).returncode:
        raise SystemExit("wheel build failed")
    wheels = list(dist.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one wheel, got {[w.name for w in wheels]}")

    if sh([PY, "-m", "pip", "install", "--no-deps", "--target", str(install),
           str(wheels[0])]).returncode:
        raise SystemExit("install failed")

    shipped = sorted(p.relative_to(install).as_posix() for p in install.rglob("*")
                     if p.is_file())
    return install, shipped


LAUNCHER = '''\
import json, pathlib, sys

TARGET = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(TARGET))
for extra in sys.argv[3:]:
    if extra not in sys.path:
        sys.path.append(extra)

import engcore

# PROVENANCE FIRST. Everything below is worthless if this is the checkout, and
# the failure is silent without this check -- which is the whole point of it.
where = pathlib.Path(engcore.__file__).resolve()
if not str(where).startswith(str(TARGET.resolve())):
    print(json.dumps({"error": "engcore came from " + str(where)}))
    raise SystemExit(2)

from engcore import api_snapshot

print(json.dumps({
    "engcore_file": str(where),
    "frozen_digest": api_snapshot.frozen_digest(),
    "full_digest": api_snapshot.digest(),
    "frozen_count": api_snapshot.frozen_only()["symbol_count"],
    "src_alias_importable": _alias(),
}))
'''

ALIAS_HELPER = '''
def _alias():
    try:
        import src.engcore  # noqa: F401
    except Exception:
        return False
    return True
'''


def main() -> int:
    work = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "D:/fwheel_api")
    work.mkdir(parents=True, exist_ok=True)

    install, shipped = build_and_install(work)
    modules = [p for p in shipped if p.endswith(".py")]
    print(f"[install] {len(shipped)} files, {len(modules)} python modules")

    top_level = sorted({p.split("/")[0] for p in shipped})
    print(f"[install] top-level names: {top_level}")

    launcher = work / "probe.py"
    body = LAUNCHER.replace("import json, pathlib, sys",
                            "import json, pathlib, sys" + ALIAS_HELPER)
    launcher.write_bytes(body.encode("utf-8"))

    site = [sysconfig.get_paths()["purelib"],
            str(ROOT / ".venv" / "Lib" / "site-packages")]
    out = sh([PY, "-S", "-E", "-X", "utf8", str(launcher), str(install), "--", *site],
             capture_output=True, cwd=str(work))
    if out.returncode != 0:
        print(out.stdout, out.stderr)
        raise SystemExit(f"wheel probe failed with {out.returncode}")
    wheel = json.loads(out.stdout.strip().splitlines()[-1])

    source = json.loads(subprocess.run(
        [PY, "-X", "utf8", "-c",
         "import json;from engcore import api_snapshot as a;"
         "print(json.dumps({'frozen_digest':a.frozen_digest(),"
         "'full_digest':a.digest(),"
         "'frozen_count':a.frozen_only()['symbol_count']}))"],
        capture_output=True, text=True, check=True, cwd=str(ROOT)).stdout)

    print()
    print("=" * 72)
    print("SOURCE vs WHEEL")
    print("=" * 72)
    print(f"  engcore imported from : {wheel['engcore_file']}")
    print(f"  source frozen digest  : {source['frozen_digest']}")
    print(f"  wheel  frozen digest  : {wheel['frozen_digest']}")
    parity = source["frozen_digest"] == wheel["frozen_digest"]
    print(f"  FROZEN API PARITY     : {'MATCH' if parity else 'MISMATCH'}")
    print(f"  frozen symbol count   : {source['frozen_count']} / {wheel['frozen_count']}")
    print(f"  src.engcore in wheel  : {wheel['src_alias_importable']}"
          f"  {'<-- MUST be False' if wheel['src_alias_importable'] else '(correct)'}")

    result = {
        "shipped_files": len(shipped),
        "python_modules": len(modules),
        "top_level_names": top_level,
        "source": source,
        "wheel": wheel,
        "frozen_api_parity": parity,
        "src_alias_absent_from_wheel": not wheel["src_alias_importable"],
    }
    out_path = ROOT / "benchmarks" / "core_api_stability" / "WHEEL_PARITY.json"
    out_path.write_bytes(json.dumps(result, indent=2, sort_keys=True).encode("utf-8"))
    print(f"\nwrote {out_path}")
    return 0 if (parity and not wheel["src_alias_importable"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
