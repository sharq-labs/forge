"""BIG 14: CalculiX's measured probe exit code is declared, pinned and validated.

Provider-free: runs in the core suite (the adapter root is a pytest pythonpath root) and in the provider env.
Kept out of tests/ so the certified mutation harness copy, which holds no providers/, never imports it.
"""

from __future__ import annotations

import os

import pytest

from engcore.providers import Availability, ProviderCapability, ProviderRegistry, ProviderStatus, executable_probe


def test_the_calculix_descriptor_declares_exactly_its_measured_probe_exit_code(monkeypatch):
    """BIG 14 F3/F7: `ccx -v` exits 201 by design (CalculiX 2.23). The declaration is pinned, and the rule refuses nonsense."""
    import forge_calculix.descriptor as ccd

    seen = {}

    def spy(capability, executable, version_argv, parse_version, **kwargs):
        seen.update(executable=executable, argv=version_argv, **kwargs)
        return lambda: ProviderStatus(capability, Availability.UNAVAILABLE, reason="spy")
    monkeypatch.setattr(ccd, "executable_probe", spy)
    ccd.register(ProviderRegistry(), provider_envs="/nowhere")
    assert seen["executable"] == "ccx" and seen["argv"] == ("-v",) and seen["accepted_exit_codes"] == (201,)
    assert ccd._version("                This is Version 2.23\n") == "2.23"
    cap = ProviderCapability("x", "demo", "process", "x", ("demo",))
    for bad in ((), (-9,), (True,), ("0",)):
        with pytest.raises(Exception, match="accepted_exit_codes"):
            executable_probe(cap, "x", (), str, accepted_exit_codes=bad)
