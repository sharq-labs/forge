"""Content binding rejects a changed image, project, dependency or thread count."""
import json
import pathlib

import pytest

from benchmarks.genesis_lite import runtime_assets_v4 as assets


def _asset(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "python_packages", lambda: {"pysr": {"version": "2.7.2", "source_sha256": "source"}})
    monkeypatch.setattr(assets, "check_read_only_asset", lambda p: pathlib.Path(p))
    exe = tmp_path / "julia"
    exe.write_bytes(b"binary")
    for name in ("Project.toml", "Manifest.toml"):
        (tmp_path / name).write_text(name)
    image = tmp_path / "test.so"
    image.write_bytes(b"image")
    env = {"PYTHON_JULIACALL_EXE": str(exe), "PYTHON_JULIACALL_PROJECT": str(tmp_path), "PYTHON_JULIACALL_THREADS": "1"}
    runtime = assets.runtime_identity(env)["content"]
    manifest = {"sysimage_sha256": assets.sha(image), "python_packages": runtime["python_packages"],
                "runtime_files": runtime["files"], "runtime_thread_env": {"PYTHON_JULIACALL_THREADS": "1"}}
    pathlib.Path(str(image) + ".manifest.json").write_text(json.dumps(manifest))
    env["PYTHON_JULIACALL_SYSIMAGE"] = str(image)
    assert assets.runtime_identity(env)["content"]["sysimage"]["sha256"] == assets.sha(image)
    return env, image


@pytest.mark.parametrize("file", ["test.so", "julia", "Project.toml", "Manifest.toml"])
def test_changed_asset_refuses(tmp_path, monkeypatch, file):
    env, _ = _asset(tmp_path, monkeypatch)
    (tmp_path / file).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="mismatch"):
        assets.runtime_identity(env)


def test_changed_threads_or_python_package_refuses(tmp_path, monkeypatch):
    env, _ = _asset(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="thread configuration"):
        assets.runtime_identity({**env, "PYTHON_JULIACALL_THREADS": "auto"})
    monkeypatch.setattr(assets, "python_packages", lambda: {"pysr": {"version": "2.7.2", "source_sha256": "edited-source"}})
    with pytest.raises(ValueError, match="Python package"):
        assets.runtime_identity(env)


def test_missing_manifest_never_becomes_an_unbound_image(tmp_path, monkeypatch):
    env, image = _asset(tmp_path, monkeypatch)
    pathlib.Path(str(image) + ".manifest.json").unlink()
    with pytest.raises(FileNotFoundError):
        assets.runtime_identity(env)


def test_thread_configuration_changes_environment_identity(monkeypatch):
    monkeypatch.setattr(assets, "python_packages", lambda: {})
    assert assets.runtime_identity({"PYTHON_JULIACALL_THREADS": "1"})["sha256"] != assets.runtime_identity({})["sha256"]


def test_formal_runtime_must_be_explicitly_bound(tmp_path, monkeypatch):
    from benchmarks.genesis_lite import pilot_v4
    path = tmp_path / "prereg.json"
    monkeypatch.setattr(pilot_v4, "PREREG", path)
    manifest = {"proposer_runtime_identity": {"sha256": "runtime-a"}}
    for content in ({}, {"proposer_runtime_identity_sha256": None}, {"proposer_runtime_identity_sha256": "runtime-b"}):
        path.write_text(json.dumps(content))
        assert "not bound" in pilot_v4.formal_runtime_check(manifest)
    path.write_text(json.dumps({"proposer_runtime_identity_sha256": "runtime-a"}))
    assert pilot_v4.formal_runtime_check(manifest) == ""
