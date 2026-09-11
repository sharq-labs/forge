"""The repository's ``src/`` directory. Not a package, and not shipped.

The distribution ships exactly one package, ``engcore``
(``[tool.setuptools.packages.find] where = ["src"]``). This file lies outside
it and is in no wheel. It exists because of a freeze.

Eleven files import the runtime through the repository root, as
``src.engcore``, and cannot be edited: each is SHA-256 byte-pinned by a frozen
experiment, and rewriting an import line would break the pin that makes "not
edited afterwards" a checkable claim.
``tests/test_trust_boundary_package_identity.py`` names them and re-reads every
pin.

Until this file said otherwise, that spelling loaded the same source files a
SECOND time under a second name: two module trees, two sets of class objects.
``isinstance`` of an ``engcore`` Quantity against the ``src.engcore`` Quantity
was False; ``CSTRInferenceForwardAdapter`` refused a ``ReactorRun`` built by a
config that used the other spelling as "not a fully declared ReactorRun"; and
every table keyed by module name had to carry both names.

So the spelling is an ALIAS now, not a copy. Importing ``src.engcore.X``
returns the module object ``engcore.X`` itself -- the same object, with its
canonical ``__name__`` and ``__spec__`` -- and never executes a file.
``__path__`` is empty, so nothing else is importable from under ``src``. New
code imports ``engcore``; the same test refuses the frozen spelling in any file
a freeze does not pin.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import os
import sys

#: Nothing under this directory is importable through ``src`` except the alias
#: below. An empty ``__path__`` also keeps the path-based finders from loading
#: ``src/engcore`` as a second package if the finder below were ever bypassed.
__path__: list[str] = []

_ALIAS = f"{__name__}.engcore"
_CANONICAL = "engcore"


class _CanonicalModuleLoader(importlib.abc.Loader):
    """Hands the import system an existing module instead of executing a file."""

    def __init__(self, module) -> None:
        self._module = module
        self._spec = module.__spec__

    def create_module(self, spec):
        return self._module

    def exec_module(self, module) -> None:
        # The import system stamps the alias spec onto whatever
        # `create_module` returned before it calls this. The module is the
        # canonical one and keeps its own spec, so anything reading
        # `__spec__.name` -- or reloading it -- sees one name.
        module.__spec__ = self._spec


class _FrozenSpellingFinder(importlib.abc.MetaPathFinder):
    """Resolves ``src.engcore[.X]`` to the canonical ``engcore[.X]`` module."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname != _ALIAS and not fullname.startswith(_ALIAS + "."):
            return None
        canonical = importlib.import_module(_CANONICAL + fullname[len(_ALIAS):])
        return importlib.util.spec_from_loader(
            fullname,
            _CanonicalModuleLoader(canonical),
            is_package=hasattr(canonical, "__path__"),
        )


# A checkout with only the repository root on the path used to reach the
# runtime through this spelling alone, and still does: when nothing else
# provides the canonical package, it is looked for beside this file.
if importlib.util.find_spec(_CANONICAL) is None:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# First on the meta path, so no path-based finder ever sees the alias. Once
# per process, including across a reload of this module.
if not any(
    type(finder).__name__ == _FrozenSpellingFinder.__name__
    and type(finder).__module__ == __name__
    for finder in sys.meta_path
):
    sys.meta_path.insert(0, _FrozenSpellingFinder())
