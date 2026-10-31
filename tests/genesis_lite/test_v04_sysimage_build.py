"""Incremental images cannot claim the identity of a different parent runtime."""
import copy

import pytest

from tools.genesis_performance.seal_sysimage import validate_parent_manifest


def manifests():
    current = {"python_packages": {"pysr": {"version": "2.7.2", "source_sha256": "python"}},
               "runtime_thread_env": {"PYTHON_JULIACALL_THREADS": "1"},
               "julia_version": "julia version 1.11.9", "cpu_target": "native",
               "runtime_files": {name: {"sha256": name} for name in
                                 ("julia_executable", "Project.toml", "Manifest.toml")}}
    return current, {**copy.deepcopy(current), "sysimage_sha256": "parent"}


def test_matching_parent_is_accepted():
    current, parent = manifests()
    validate_parent_manifest(parent, current, "parent")


@pytest.mark.parametrize("field", ["sysimage_sha256", "python_packages", "runtime_thread_env", "julia_version", "cpu_target"])
def test_changed_parent_identity_refuses(field):
    current, parent = manifests()
    parent[field] = "different"
    with pytest.raises(ValueError, match="parent image"):
        validate_parent_manifest(parent, current, "parent")


@pytest.mark.parametrize("file", ["julia_executable", "Project.toml", "Manifest.toml"])
def test_changed_parent_runtime_bytes_refuse(file):
    current, parent = manifests()
    parent["runtime_files"][file]["sha256"] = "different"
    with pytest.raises(ValueError, match="runtime file"):
        validate_parent_manifest(parent, current, "parent")


def test_missing_parent_metadata_refuses():
    current, _ = manifests()
    with pytest.raises(ValueError, match="python_packages"):
        validate_parent_manifest({"sysimage_sha256": "parent"}, current, "parent")
