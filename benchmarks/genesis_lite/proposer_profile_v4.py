"""Opt-in development profiling wrapper around the unchanged v0.2-pinned host.

Phase labels/runtime introspection come from the proposer and are UNTRUSTED
diagnostics. Parent timestamps and /proc sampling remain the timing authority.
Never used to grant validity, scientific support or isolation verification.
"""
from __future__ import annotations

import json
import pathlib
import runpy
import sys

out = sys.stdout.buffer


def send(label, event, **extra):
    out.write(json.dumps({"op": "diagnostic", "label": label, "event": event, **extra}).encode() + b"\n")
    out.flush()


def profile(frame, event, arg):
    if event not in ("call", "return"):
        return
    name, path = frame.f_code.co_name, frame.f_code.co_filename.replace("\\", "/")
    label = None
    if path.endswith("/juliacall/__init__.py") and name == "init":
        label = "juliacall_initialization"
    elif path.endswith("/pysr/julia_import.py") and name == "<module>":
        label = "julia_dependency_loading_inclusive"
    elif path.endswith("/pysr/sr.py") and name in ("fit", "_run", "get_hof", "sympy"):
        label = "pysr_" + name
    elif path.endswith("/proposer_host.py") and name == "resolve":
        label = "python_arm_resolution"
    if label:
        send(label, event)
    if label == "julia_dependency_loading_inclusive" and event == "return":
        try:
            jl = sys.modules["juliacall"].Main
            send("runtime", "info", julia=str(jl.VERSION), threads=int(jl.seval("Threads.nthreads()")),
                 gc_threads=int(jl.seval("Threads.ngcthreads()")),
                 image=str(jl.seval("unsafe_string(Base.JLOptions().image_file)")),
                 symbolic_regression=str(jl.seval("string(Base.pkgversion(SymbolicRegression))")))
            jl.seval("Base.cumulative_compile_timing(true)")
        except Exception as exc:
            send("runtime_probe_error", "info", error=type(exc).__name__ + ": " + str(exc)[:200])
    if label == "pysr_fit" and event in ("call", "return"):
        try:
            jl = sys.modules["juliacall"].Main
            send("compile_counter", event, nanoseconds=list(jl.seval("Base.cumulative_compile_time_ns()")))
        except Exception:
            pass


sys.setprofile(profile)
send("python_wrapper", "ready")
runpy.run_path(str(pathlib.Path(__file__).with_name("proposer_host.py")), run_name="__main__")
