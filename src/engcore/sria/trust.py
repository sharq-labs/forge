"""Import-graph trust boundary.

The Scientific Core's docstring has always said that nothing in it may import
an LLM provider. A docstring is not a boundary — it is a hope. This module
turns it into something a test can fail on.

**What this is.** A CI architectural guardrail: it catches an LLM dependency
entering the scientific path during review, when removing it is still cheap.
It is not a sandbox, not a runtime restriction, and not a security proof.
Nothing here prevents code from reaching a network or from importing a
provider through a dynamic mechanism the scanner cannot see (``importlib``,
``exec``, a re-exporting shim). It raises the cost of the mistake that
actually happens — someone adds a convenient import — and leaves adversarial
evasion out of scope.

The check is a static AST scan of the package source rather than an inspection
of ``sys.modules``, because a runtime scan only sees what happened to be
imported in that process: a lazily-imported provider inside a rarely-taken
branch would pass a runtime check and still be a live dependency.

Why this matters beyond tidiness: the platform's core claim is that it remains
usable if every AI provider disappears, and that a language model is never the
numerical truth layer. Both claims are falsified the moment an LLM import
appears anywhere the scientific path can reach.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, Iterator

from .errors import TrustBoundaryViolation

#: Top-level module names that must not appear anywhere in the scientific path.
FORBIDDEN_ROOTS: frozenset[str] = frozenset(
    {
        "anthropic",
        "openai",
        "cohere",
        "litellm",
        "ollama",
        "langchain",
        "langchain_core",
        "langchain_community",
        "llama_cpp",
        "llama_index",
        "transformers",
        "sentence_transformers",
        "google.generativeai",
        "vertexai",
        "mistralai",
        "replicate",
        "huggingface_hub",
    }
)


def _python_files(package_dir: Path) -> Iterator[Path]:
    yield from sorted(package_dir.rglob("*.py"))


def _imported_roots(source: str, filename: str) -> set[str]:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:  # pragma: no cover - a broken file is a real bug
        raise TrustBoundaryViolation(
            f"cannot parse {filename} for trust analysis: {exc}"
        ) from exc

    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import: inside our own package by
            # construction, so it cannot introduce an external dependency.
            if node.level == 0 and node.module:
                roots.add(node.module)
    return roots


def _matches_forbidden(module: str) -> str | None:
    parts = module.split(".")
    for forbidden in FORBIDDEN_ROOTS:
        f_parts = forbidden.split(".")
        if parts[: len(f_parts)] == f_parts:
            return forbidden
    return None


def scan_imports(package_dir: Path) -> dict[str, set[str]]:
    """Map every module file to the absolute modules it imports."""
    found: dict[str, set[str]] = {}
    for path in _python_files(package_dir):
        found[str(path)] = _imported_roots(
            path.read_text(encoding="utf-8"), str(path)
        )
    return found


def find_forbidden_imports(
    package_dirs: Iterable[Path],
) -> tuple[tuple[str, str, str], ...]:
    """Return ``(file, imported_module, forbidden_root)`` for every violation."""
    violations: list[tuple[str, str, str]] = []
    for package_dir in package_dirs:
        for filename, modules in scan_imports(Path(package_dir)).items():
            for module in sorted(modules):
                forbidden = _matches_forbidden(module)
                if forbidden is not None:
                    violations.append((filename, module, forbidden))
    return tuple(violations)


def assert_no_llm_dependencies(package_dirs: Iterable[Path]) -> None:
    """Raise if any scientific-path module imports an LLM provider."""
    violations = find_forbidden_imports(package_dirs)
    if violations:
        detail = "; ".join(
            f"{Path(f).name} imports {m} (forbidden root {root})"
            for f, m, root in violations
        )
        raise TrustBoundaryViolation(
            f"LLM dependency found in the scientific import graph: {detail}. "
            f"A language model is never the numerical truth layer."
        )
