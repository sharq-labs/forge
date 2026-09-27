"""BIG 14 review F1: OpenFOAM's own version probe requires exit 0 whatever its output says.

Provider-free: runs in the core suite (the adapter root is a pytest pythonpath root) and in the provider env.
Kept out of tests/ so the certified mutation harness copy, which holds no providers/, never imports it.
"""

from __future__ import annotations

import os

import pytest

from engcore.providers import Availability, ProviderCapability, ProviderRegistry, ProviderStatus, executable_probe


@pytest.mark.skipif(os.name != "posix", reason="a shell-script stand-in for icoFoam needs a POSIX host (CI is Linux)")
@pytest.mark.parametrize("exit_code, available", ((0, True), (1, False)))
def test_the_openfoam_probe_requires_exit_zero_whatever_its_output_says(tmp_path, exit_code, available):
    """BIG 14 F1: OpenFOAM does not go through executable_probe, so its own probe must refuse a failed run."""
    import json
    import stat

    import forge_openfoam.descriptor as ofd

    prefix = tmp_path / "openfoam"
    (prefix / "bin").mkdir(parents=True)
    (prefix / "conda-meta").mkdir()
    (prefix / "conda-meta" / "stub-1-0.json").write_text(json.dumps({"name": "stub", "version": "1", "build": "0", "sha256": "0" * 64}))
    exe = prefix / "bin" / "icoFoam"
    exe.write_text("\n".join(("#!/bin/sh", "echo 'Build  : OpenFOAM-v2412'", f"exit {exit_code}", "")))
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    reg = ProviderRegistry()
    ofd.register(reg, provider_envs=str(tmp_path))
    status = reg.status("openfoam")
    assert status.available is available, status.reason
    if available:
        assert status.version == "v2412" and status.digest
    else:
        assert not status.digest and "exited 1 (accepted [0])" in status.reason
