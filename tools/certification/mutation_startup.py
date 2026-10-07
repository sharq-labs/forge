"""Immutable shard startup inputs; no pytest, test or scientific imports."""
from __future__ import annotations

from dataclasses import dataclass
import os
import pathlib
import stat
import sys
from types import MappingProxyType
from typing import Mapping

# External entry-point plugins are unnecessary for the selected mutation targets.
# Builtins (including fixtures/JUnit) and repository conftest remain enabled.
MUTATION_ENVIRONMENT = MappingProxyType({
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
})
V4_PYTEST_FLAGS = ("-m", "pytest", "-q", "-p", "no:cacheprovider", "--runxfail")
FORMAL_PYTEST_FLAGS = ("-X", "utf8", "-m", "pytest")


def _executable_identity(path):
    info = pathlib.Path(path).stat()
    if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111:
        raise RuntimeError("mutation interpreter is not an executable regular file")
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


@dataclass(frozen=True)
class StartupInputs:
    executable: str
    identity: tuple
    environment: Mapping[str, str]

    @classmethod
    def capture(cls, *, executable=None, inherited=None):
        # Keep the venv path: resolving its symlink changes site initialization.
        path = os.path.abspath(sys.executable if executable is None else executable)
        values = dict(os.environ if inherited is None else inherited)
        return cls(path, _executable_identity(path), MappingProxyType(values))

    def check(self):
        if _executable_identity(self.executable) != self.identity:
            raise RuntimeError("mutation interpreter identity changed within shard")
