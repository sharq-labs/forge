"""One package identity.

TB-1 of the trust-boundary hardening sprint.

The distribution ships exactly one package, ``engcore``
(``[tool.setuptools.packages.find] where = ["src"]``). In a checkout the same
files were ALSO importable through the repository root as the frozen
spelling -- ``src/__init__.py`` made ``src`` a regular package and pytest's
``pythonpath`` put the root on ``sys.path`` -- and the two spellings built two
module trees with two sets of class objects. ``isinstance`` of a Quantity from
one against the Quantity of the other was False, and module-name-keyed tables
(``engcore.domains``' freeze exemptions, the MCP model walk) had to carry both.

That spelling cannot simply be deleted: eleven files that use it are SHA-256
byte-pinned by frozen experiments, and rewriting their import lines would break
the pins that make "not edited afterwards" a checkable claim. So
``src/__init__.py`` now resolves the frozen spelling to the canonical module
objects instead of loading the files a second time, and every file that is not
pinned uses ``engcore``.

The frozen spelling is assembled at runtime below rather than written out, so
the sweep in this file does not have to exempt the file that runs it.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import pathlib
import re
import subprocess
import sys

import pytest

import engcore
from engcore.scientific.units.quantity import Quantity

REPO = pathlib.Path(__file__).resolve().parents[1]
FROZEN = "src" + ".engcore"

#: The only files that may still spell the frozen namespace, each with the
#: frozen experiment config whose digest table pins its bytes.
#: ``test_every_remaining_frozen_spelling_is_pinned_by_a_freeze`` reads the pin
#: off that table rather than trusting this mapping, so an entry expires the
#: day its freeze does.
PINNED_FROZEN_SPELLERS: dict[str, str] = {
    "experiments/electrical_e1/e1_harness.py": "experiments/electrical_e2/e2_config.py",
    "experiments/electrical_e1/e1_model.py": "experiments/electrical_e2/e2_config.py",
    "experiments/electrical_e1/e1_run.py": "experiments/electrical_e2/e2_config.py",
    "tests/test_sria_e1_electrical.py": "experiments/electrical_e2/e2_config.py",
    "experiments/electrical_e2/e2_harness.py": "experiments/electrical_e3/e3_config.py",
    "experiments/electrical_e2/e2_model.py": "experiments/electrical_e3/e3_config.py",
    "experiments/electrical_e2/e2_run.py": "experiments/electrical_e3/e3_config.py",
    "tests/test_sria_e2_model_adequacy.py": "experiments/electrical_e3/e3_config.py",
    "experiments/thermal_t1/t1_run.py": "experiments/thermal_t2/t2_config.py",
    "experiments/thermal_t1/t1_truth.py": "experiments/thermal_t2/t2_config.py",
    "experiments/thermal_t2/t2_run.py": "experiments/thermal_t3/t3_config.py",
}

_ESCAPED = re.escape(FROZEN)
_SPELLING = re.compile(
    rf"(?:\bfrom\s+{_ESCAPED}\b|\bimport\s+{_ESCAPED}\b"
    rf"|\bfrom\s+src\s+import\s+engcore\b|[\"']{_ESCAPED}\b)"
)
_SCANNED_ROOTS = ("src", "tests", "experiments", "benchmarks")
_DIGEST = re.compile(r"\b[0-9a-f]{64}\b")


def _python_sources() -> list[pathlib.Path]:
    found = []
    for root in _SCANNED_ROOTS:
        for path in (REPO / root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            found.append(path)
    return sorted(found)


# ---- identity -------------------------------------------------------------
def test_the_frozen_spelling_is_the_canonical_package_not_a_copy():
    frozen_quantity = importlib.import_module(
        f"{FROZEN}.scientific.units.quantity"
    ).Quantity

    assert importlib.import_module(FROZEN) is engcore
    assert frozen_quantity is Quantity
    assert isinstance(Quantity(1.0, "kelvin"), frozen_quantity)
    assert frozen_quantity.__module__ == "engcore.scientific.units.quantity"


def test_a_class_reached_through_the_frozen_spelling_reports_the_canonical_module():
    """Module-name-keyed tables only ever see one name.

    The frozen T1 solver is looked up by its constructing module's name for its
    declared exemption, and the repository's solver/model sweeps filter classes
    by ``__module__``. Both used to depend on which spelling imported first.
    """
    frozen_solver = importlib.import_module(
        f"{FROZEN}.domains.thermal.conduction1d.solver"
    )
    canonical_solver = importlib.import_module(
        "engcore.domains.thermal.conduction1d.solver"
    )
    assert frozen_solver is canonical_solver
    assert frozen_solver.Conduction1DSolver.__module__ == (
        "engcore.domains.thermal.conduction1d.solver"
    )
    assert frozen_solver.__spec__.name == "engcore.domains.thermal.conduction1d.solver"


@pytest.mark.parametrize("first", ["frozen", "canonical"])
def test_identity_does_not_depend_on_which_spelling_is_imported_first(first):
    """In a fresh interpreter, so this process's import order cannot help."""
    order = (FROZEN, "engcore") if first == "frozen" else ("engcore", FROZEN)
    code = (
        "import importlib, sys\n"
        f"first, second = {order!r}\n"
        "a = importlib.import_module(first + '.scientific.consensus')\n"
        "b = importlib.import_module(second + '.scientific.consensus')\n"
        "assert a is b, (a, b)\n"
        "assert a.CrossSolverConsensus is b.CrossSolverConsensus\n"
        f"prefix = {FROZEN!r}\n"
        "split = sorted(\n"
        "    name for name, module in sys.modules.items()\n"
        "    if name.startswith(prefix)\n"
        "    and module is not sys.modules.get(name[len('src.'):])\n"
        ")\n"
        "assert not split, split\n"
        "canonical = sorted(n for n in sys.modules if n.startswith('engcore'))\n"
        "assert canonical, 'nothing canonical was imported'\n"
        "print('ONE IDENTITY', len(canonical))\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "src"), str(REPO)])
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr[-3000:]
    assert "ONE IDENTITY" in done.stdout


def test_src_is_not_a_package_of_its_own():
    """``src`` holds nothing but the frozen alias; it is not a second namespace."""
    src = importlib.import_module("src")
    assert list(src.__path__) == []
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.crafty")
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(
        r'\[tool\.setuptools\.packages\.find\]\s*\nwhere\s*=\s*\["src"\]', pyproject
    )


# ---- one spelling in every file that is free to use it -----------------------
def test_no_unpinned_file_spells_the_frozen_namespace():
    offenders = []
    for path in _python_sources():
        rel = path.relative_to(REPO).as_posix()
        if rel in PINNED_FROZEN_SPELLERS:
            continue
        text = path.read_bytes().decode("utf-8-sig")
        for number, line in enumerate(text.splitlines(), 1):
            if _SPELLING.search(line):
                offenders.append(f"{rel}:{number}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_every_remaining_frozen_spelling_is_pinned_by_a_freeze():
    """The exemption is read off the freeze, not remembered."""
    for rel, config in sorted(PINNED_FROZEN_SPELLERS.items()):
        data = (REPO / rel).read_bytes()
        assert _SPELLING.search(data.decode("utf-8-sig")), (
            f"{rel} no longer spells the frozen namespace; drop its exemption"
        )
        actual = hashlib.sha256(data).hexdigest()
        lines = (REPO / config).read_bytes().decode("utf-8").splitlines()
        pinned = None
        for index, line in enumerate(lines):
            if f'"{rel}"' in line:
                for candidate in lines[index : index + 4]:
                    match = _DIGEST.search(candidate)
                    if match:
                        pinned = match.group(0)
                        break
                break
        assert pinned is not None, f"{config} does not pin {rel}"
        assert pinned == actual, f"{rel} is no longer the bytes {config} froze"
