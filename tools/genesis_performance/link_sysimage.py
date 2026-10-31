"""Link-only GCC-argv adapter to the EXACT Julia distribution's bundled LLD.

PackageCompiler's incremental image already contains native object code; no C
compilation is needed. Reject compilation requests instead of pretending to be
a general C compiler. No system compiler or loader installation is required.
"""
import os
import pathlib
import sys

lld = pathlib.Path("/opt/forge-mvp-20261028/.venv/julia_env/pyjuliapkg/install/libexec/julia/lld")
args = sys.argv[1:]
if "-shared" not in args or any(a == "-c" or a.endswith((".c", ".cpp")) for a in args):
    raise SystemExit("this adapter accepts only PackageCompiler shared-object linking")
link = []
for arg in args:
    if arg in ("-m64", "-march=x86-64", "-fPIC"):
        continue
    link.extend(arg[4:].split(",") if arg.startswith("-Wl,") else [arg])
os.execv(str(lld), [str(lld), "-flavor", "gnu", *link])
