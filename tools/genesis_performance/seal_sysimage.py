"""Bind an operator-built public-workload sysimage, without freezing a preregistration."""
import argparse
import json
import pathlib
import subprocess

from benchmarks.genesis_lite.runtime_assets_v4 import python_packages, sha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--build", required=True)
    ap.add_argument("--mode", choices=("packages", "functions"), required=True)
    ap.add_argument("--cpu-target", required=True)
    args = ap.parse_args()
    output = pathlib.Path(args.image + ".manifest.json")
    if output.exists():
        raise FileExistsError("refusing to replace an immutable asset manifest")
    build = pathlib.Path(args.build)
    project = pathlib.Path("/opt/forge-mvp-20261028/.venv/julia_env")
    binary = project / "pyjuliapkg/install/bin/julia"
    files = {"julia_executable": binary, "Project.toml": project / "Project.toml", "Manifest.toml": project / "Manifest.toml"}
    # The experiment's environment is never resolved/modified by the build.
    for name in ("Project.toml", "Manifest.toml"):
        assert sha(project / name) == sha(build / "project" / name), f"build changed {name}"
    scripts = ["setup_build.jl", "build_sysimage.jl", "precompile_workload.jl", "link_sysimage.py", "build.sh"]
    doc = {"schema": "forge.development.sysimage/1", "purpose": "public synthetic precompilation only",
           "sysimage_sha256": sha(args.image), "mode": args.mode, "cpu_target": args.cpu_target,
           "julia_version": subprocess.check_output([str(binary), "--version"], text=True).strip(),
           "base_sysimage_sha256": sha(project / "pyjuliapkg/install/lib/julia/sys.so"),
           "linker_sha256": sha(project / "pyjuliapkg/install/libexec/julia/lld"),
           "python_packages": python_packages(),
           "runtime_files": {k: {"path": str(p), "sha256": sha(p)} for k, p in files.items()},
           "runtime_thread_env": {"PYTHON_JULIACALL_THREADS": "1", "JULIA_NUM_GC_THREADS": "1",
                                  "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"},
           "build_thread_env": {"JULIA_NUM_THREADS": "1", "JULIA_NUM_GC_THREADS": "1", "JULIA_NUM_PRECOMPILE_TASKS": "1", "JULIA_IMAGE_THREADS": "4"},
           "scripts": {name: sha(build / name) for name in scripts},
           "compiler_project": (build / "compiler/Project.toml").read_text(),
           "compiler_manifest": (build / "compiler/Manifest.toml").read_text(),
           "runtime_project": (project / "Project.toml").read_text(),
           "runtime_manifest": (project / "Manifest.toml").read_text(),
           "state_policy": "workload executes in a trace subprocess; no fitted state is loaded into image builder"}
    output.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    pathlib.Path(args.image).chmod(0o444)
    output.chmod(0o444)
    print(json.dumps({"image": args.image, "sha256": doc["sysimage_sha256"], "manifest_sha256": sha(output)}))


if __name__ == "__main__":
    main()
