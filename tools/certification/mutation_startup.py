"""Immutable shard startup inputs; no pytest, test or scientific imports."""
from __future__ import annotations

from dataclasses import dataclass
import os
import pathlib
import shlex
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
FORMAL_XDIST_GUARD = "tools.certification.formal_xdist_guard"


def formal_xdist_worker_spec(workers, executable):
    """N local xdist workers on the shard's own interpreter, each started with ``-X utf8``.

    Serial Formal is one ``python -X utf8`` process. ``-n N`` would start bare workers without
    the flag; this ``--tx`` spec gives every worker the same interpreter and flag without adding
    a PYTHON* variable to the sealed child environment.
    """
    if "//" in str(executable):     # execnet splits specs on "//": the python value would be lost
        raise ValueError("the shard interpreter path cannot be expressed as an xdist --tx spec")
    return f"{workers}*popen//python={shlex.quote(str(executable))} -X utf8"


def formal_xdist_flags(workers, sentinel, executable):
    """Formal-only pytest-xdist: explicit plugins, file-level distribution, no worker restarts.

    Appended only when a Formal shard asks for more than one pytest worker; the default (one
    worker) command is unchanged. The guard plugin's sentinel is the infrastructure evidence.
    """
    if not isinstance(workers, int) or isinstance(workers, bool) or workers < 2:
        raise ValueError("Formal pytest-xdist needs an integer worker count of at least 2")
    return ("-p", "xdist.plugin", "--tx", formal_xdist_worker_spec(workers, executable),
            "--dist", "loadfile", "--max-worker-restart=0", "-p", FORMAL_XDIST_GUARD,
            f"--forge-xdist-sentinel={sentinel}")


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
