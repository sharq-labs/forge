"""Dependency and interpreter identity, read at run time and never assumed.

P10 asks a buyer's question: *which exact external scientific implementation
produced this number?* For a subprocess provider the answer is the binary's
own banner, which is what ``NgspiceInvocation.probe_version`` reads. For an
in-process Python provider the answer is larger, because the provider is not
one program: PyBaMM's answer is also CasADi's answer, and NumPy's, and the
interpreter's.

So this module records a **set** of versions, digests it, and hands the digest
to :class:`~engcore.providers.contract.ProviderIdentity`. The versions are read
from installed distribution metadata at the moment of the run. Nothing here is
hard-coded, for the reason ngspice states: a pinned version string makes
provenance lie the first time the environment moves, and provenance that can
lie is worse than provenance that is absent.

Why the platform is recorded and the path is not
-------------------------------------------------
``ngspice.py`` deliberately keeps the executable's *location* out of every
scientific record: where a binary sits cannot change what a result means. The
same rule is applied here and reaches a different conclusion about a different
fact. A library *version* is not a location — it selects which equations and
which numerics ran — so it belongs in the record. The interpreter version and
the platform tag are recorded for the same reason: a CasADi wheel is
platform-specific and its floating-point tail is not promised to be identical
across them.

What is NOT recorded: the virtual environment's path, the machine's name, the
user, the working directory. None of them can change a number, and each of them
would make an otherwise identical run look different.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from typing import Any, Mapping

from .contract import digest_of

#: Distributions whose version is recorded whenever they are present. Read as
#: a superset: a host without PyBOP records no PyBOP version and says so by
#: the key's absence rather than by a null that could be read as "0".
RECORDED_DISTRIBUTIONS = (
    "pybamm",
    "pybop",
    "salib",
    "casadi",
    "numpy",
    "scipy",
)


def distribution_version(name: str) -> str | None:
    """The installed version of ``name``, or ``None`` when it is absent.

    ``None`` rather than a placeholder. "Not installed" and "installed at an
    unknown version" are different facts, and a string like ``"unknown"`` in a
    digested record would make them the same one.
    """
    import importlib.metadata as md

    try:
        return md.version(name)
    except Exception:
        return None


@dataclass(frozen=True)
class EnvironmentIdentity:
    """The interpreter and the dependency versions a provider ran on top of."""

    python_version: str
    platform_tag: str
    distributions: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "distributions",
            dict(sorted((str(k), str(v)) for k, v in self.distributions.items())),
        )

    @classmethod
    def capture(cls, names: tuple[str, ...] = RECORDED_DISTRIBUTIONS) -> "EnvironmentIdentity":
        found = {}
        for name in names:
            version = distribution_version(name)
            if version is not None:
                found[name] = version
        return cls(
            python_version=platform.python_version(),
            platform_tag=f"{sys.platform}-{platform.machine()}",
            distributions=found,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "python_version": self.python_version,
            "platform_tag": self.platform_tag,
            "distributions": dict(self.distributions),
        }

    def digest(self) -> str:
        return digest_of(self.to_dict())

    def version_of(self, name: str) -> str | None:
        return self.distributions.get(name)

    def differences_from(self, other: "EnvironmentIdentity") -> tuple[str, ...]:
        """Every field that moved, named. Used by replay to record drift."""
        out: list[str] = []
        if self.python_version != other.python_version:
            out.append(
                f"python_version: {self.python_version} -> {other.python_version}"
            )
        if self.platform_tag != other.platform_tag:
            out.append(f"platform_tag: {self.platform_tag} -> {other.platform_tag}")
        for name in sorted(set(self.distributions) | set(other.distributions)):
            before = self.distributions.get(name)
            after = other.distributions.get(name)
            if before != after:
                out.append(f"{name}: {before} -> {after}")
        return tuple(out)


__all__ = [
    "RECORDED_DISTRIBUTIONS",
    "EnvironmentIdentity",
    "distribution_version",
]
