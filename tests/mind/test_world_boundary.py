"""GEN2-BR1 authority boundary of ``engcore.mind.world`` (static, no execution of the Mind).

The world layer reads authoritative records and decides action feasibility only.  These tests pin, by reading the
source, that it cannot reach an escrow, a benchmark world, a transport, a language model, a provider adapter, the
product layer or pint; that nothing certified (or anything outside the mind package) imports it; that the Gen1
packages and ``engcore.mind`` do not re-export it; and that the generic code carries no fixture domain vocabulary.
"""

from __future__ import annotations

import ast
import pathlib
import re

import engcore.mind.world as world_pkg

SRC = pathlib.Path(world_pkg.__file__).resolve().parent
ENGCORE = SRC.parents[1]
FORBIDDEN_PREFIXES = ("engcore.blindfold", "engcore.mcp", "engcore.product", "engcore.planning", "engcore.providers.",
                      "benchmarks", "flagships", "pint", "anthropic", "openai", "ax", "botorch", "pysindy", "pysr")
#: The provider authority's own vocabularies and digest rule are read; adapter packages, selection and execution are not.
ALLOWED_PROVIDER_MODULES = ("engcore.providers.catalog", "engcore.providers.health", "engcore.providers.identity")
DOMAIN_WORDS = ("battery", "soc", "hvac", "drone", "motor", "compressor", "thrust", "voltage", "ohm", "celsius", "degc")


def _modules():
    return sorted(SRC.glob("*.py"))


def _imports(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_bytes().decode("utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def _forbidden(name: str) -> bool:
    if name in ALLOWED_PROVIDER_MODULES:
        return False
    return any(name.startswith(p) if p.endswith(".") else name == p or name.startswith(p + ".")
               for p in FORBIDDEN_PREFIXES)


def test_the_world_layer_imports_no_escrow_transport_language_model_or_adapter():
    assert _forbidden("engcore.blindfold.escrow") and _forbidden("engcore.providers.selection")
    assert not _forbidden("engcore.providers.catalog") and not _forbidden("engcore.scientific")
    for path in _modules():
        for name in _imports(path):
            assert not _forbidden(name), f"{path.name} imports {name}"


def test_nothing_outside_the_world_package_imports_it():
    for path in ENGCORE.rglob("*.py"):
        if SRC in path.parents:
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        assert "engcore.mind.world" not in text and "mind.world" not in text, path


def test_gen1_and_mind_packages_do_not_reexport_the_world():
    for init in (ENGCORE / "mind" / "__init__.py", ENGCORE / "mind" / "repsem" / "__init__.py",
                 ENGCORE / "mind" / "minimal" / "__init__.py"):
        assert "world" not in init.read_bytes().decode("utf-8").split('"""')[-1]


def test_the_generic_code_carries_no_fixture_domain_vocabulary():
    for path in _modules():
        text = path.read_bytes().decode("utf-8").lower()
        found = [w for w in DOMAIN_WORDS if re.search(rf"\b{w}\b", text)]
        assert not found, f"{path.name} mentions {found}"


def test_sources_are_utf8_lf_without_bom():
    for path in _modules():
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw, path.name
