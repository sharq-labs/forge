"""Content binding for Julia runtime assets; no scientific authority or cache.

Sysimages must have a build manifest, match the current interpreter packages and
project bytes, and be root-owned below /opt with no group/other write permission.
The isolation verifier separately checks the actual read-only exposure per child.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import pathlib
import stat


def sha(path):
    with pathlib.Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def python_packages():
    result = {}
    for name in ("pysr", "juliacall", "juliapkg"):
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = {"version": "NOT_INSTALLED"}
            continue
        files = {str(p): sha(dist.locate_file(p)) for p in dist.files or ()
                 if str(p).startswith(name + "/") and str(p).endswith((".py", ".json"))}
        result[name] = {"version": dist.version, "source_sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}
    return result


def check_read_only_asset(path):
    path = pathlib.Path(path).resolve()
    if not path.is_relative_to("/opt"):
        raise ValueError("Julia sysimage must live below /opt")
    for part in (path, *path.parents):
        s = part.stat()
        if s.st_uid != 0 or s.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError(f"Julia asset is not root-controlled: {part}")
        if part == pathlib.Path("/opt"):
            break
    return path


def runtime_identity(env):
    from .isolated_host import THREAD_ENV
    effective = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", **THREAD_ENV, **dict(env)}
    identity = {"proposer_env": effective, "python_packages": python_packages(), "files": {}}
    files = identity["files"]
    exe = env.get("PYTHON_JULIACALL_EXE")
    project = env.get("PYTHON_JULIACALL_PROJECT")
    if bool(exe) != bool(project):
        raise ValueError("Julia executable and project must be specified together")
    if exe:
        files["julia_executable"] = {"path": str(pathlib.Path(exe).resolve()), "sha256": sha(exe)}
        for name in ("Project.toml", "Manifest.toml"):
            path = pathlib.Path(project) / name
            files[name] = {"path": str(path.resolve()), "sha256": sha(path)}
    image = env.get("PYTHON_JULIACALL_SYSIMAGE")
    if image:
        image = check_read_only_asset(image)
        manifest_path = check_read_only_asset(str(image) + ".manifest.json")
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
        if manifest["sysimage_sha256"] != sha(image):
            raise ValueError("sysimage digest mismatch")
        if manifest["python_packages"] != identity["python_packages"]:
            raise ValueError("sysimage Python package identity mismatch")
        for name in ("julia_executable", "Project.toml", "Manifest.toml"):
            if manifest["runtime_files"][name]["sha256"] != files.get(name, {}).get("sha256"):
                raise ValueError(f"sysimage runtime mismatch: {name}")
        for name, value in manifest["runtime_thread_env"].items():
            if effective.get(name) != value:
                raise ValueError(f"sysimage thread configuration mismatch: {name}")
        identity["sysimage"] = {"path": str(image), "sha256": manifest["sysimage_sha256"],
                               "build_manifest_sha256": hashlib.sha256(raw).hexdigest(), "build": manifest}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return {"sha256": digest, "content": identity}
