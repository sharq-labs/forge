"""Unsupported launchers must refuse; a portable probe is not an isolation proof."""

from types import SimpleNamespace

import pytest

from engcore.blindfold import isolation


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_non_linux_launcher_refuses_without_privilege_or_namespace_probe(monkeypatch, platform):
    monkeypatch.setattr(isolation, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(isolation, "os", SimpleNamespace())
    def forbidden(*args, **kwargs):
        pytest.fail("unsupported platform must not launch namespace commands")
    monkeypatch.setattr(isolation.subprocess, "run", forbidden)
    ok, why = isolation.isolation_support()
    assert ok is False
    assert "Linux" in why


def test_linux_non_root_remains_unsupported(monkeypatch):
    monkeypatch.setattr(isolation, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(isolation, "os", SimpleNamespace(geteuid=lambda: 1000))
    ok, why = isolation.isolation_support()
    assert ok is False and "root" in why


def test_linux_root_without_namespace_tools_remains_unsupported(monkeypatch):
    monkeypatch.setattr(isolation, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(isolation, "os", SimpleNamespace(geteuid=lambda: 0))
    monkeypatch.setattr(isolation.shutil, "which", lambda name: None)
    ok, why = isolation.isolation_support()
    assert ok is False and "missing tools" in why
