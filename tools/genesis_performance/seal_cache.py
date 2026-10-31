"""Bind import-only native Julia caches at their final immutable location."""
import json
import pathlib

from benchmarks.genesis_lite.runtime_assets_v4 import python_packages, sha


def main():
    cache = pathlib.Path("/opt/forge-julia-cache-20261031")
    assert cache.resolve() == cache and cache.is_dir()
    manifest = cache / "asset-manifest.json"
    assert not manifest.exists(), "refuse overwriting a sealed asset"
    project = pathlib.Path("/opt/forge-mvp-20261028/.venv/julia_env")
    files = {"julia_executable": project / "pyjuliapkg/install/bin/julia",
             "Project.toml": project / "Project.toml", "Manifest.toml": project / "Manifest.toml"}
    paths = sorted(cache.rglob("*"))
    assert all(not p.is_symlink() for p in paths)
    doc = {"schema": "forge.development.immutable-julia-cache/1", "purpose": "import-only; no Forge data or fitted state",
           "files": {str(p.relative_to(cache)): sha(p) for p in paths if p.is_file()},
           "python_packages": python_packages(), "build_script_sha256": sha(pathlib.Path(__file__).with_name("build_cache.sh")),
           "runtime_files": {k: {"path": str(p), "sha256": sha(p)} for k, p in files.items()},
           "cpu_target": "native", "runtime_thread_env": {"PYTHON_JULIACALL_THREADS": "1", "JULIA_NUM_GC_THREADS": "1"}}
    manifest.write_text(json.dumps(doc, sort_keys=True, indent=2), encoding="utf-8")
    for path in [*paths, manifest, cache]:
        path.chmod(0o555 if path.is_dir() else 0o444)
    print(json.dumps({"manifest_sha256": sha(manifest), "files": len(doc["files"])}))


if __name__ == "__main__":
    main()
