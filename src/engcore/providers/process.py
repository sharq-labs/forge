"""Safe boundary for external solver processes.

* argv lists only -- never a shell string; no user-provided shell is executed;
* a fresh, bounded workspace per execution; generated file names are sanitized;
* an explicit, minimal process environment (no inherited environment leakage);
* timeout with termination of the whole child process group;
* every input file and every output file bound by sha256; stdout/stderr bound by
  digest with bounded tails kept for diagnostics;
* an output counts only if THIS execution created or changed it: a file present
  before the run and left untouched (stale), or edited after the run (foreign),
  is refused by :meth:`ProcessWorkspace.read_output`.

Exit code 0 is recorded, not interpreted: the provider adapter must still check
convergence and parse outputs before anything is a result.  The workspace path
is operational; identity is the CONTENT (see :mod:`engcore.providers.identity`).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Mapping

from .identity import content_digest
from .records import ProviderRefusal

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$")
TAIL = 4000


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_relative(name: str) -> str:
    if not _SAFE_NAME.fullmatch(name) or any(part in ("", ".", "..") for part in name.split("/")):
        raise ProviderRefusal(f"generated file name {name!r} is not a safe relative path")
    return name


@dataclass(frozen=True)
class GeneratedFile:
    name: str
    content: bytes

    def __post_init__(self) -> None:
        safe_relative(self.name)
        if not isinstance(self.content, bytes):
            raise ProviderRefusal("generated file content must be bytes (exact, digest-bound)")

    @property
    def digest(self) -> str:
        return _sha(self.content)


@dataclass(frozen=True)
class ProcessInvocation:
    executable: str
    executable_digest: str
    version: str
    args: tuple[str, ...]
    inputs: tuple[GeneratedFile, ...]
    environment: tuple[tuple[str, str], ...]
    timeout_s: float
    expected_outputs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not os.path.isabs(self.executable):
            raise ProviderRefusal("the executable must be an exact absolute path from provider discovery")
        if any(not isinstance(a, str) for a in self.args):
            raise ProviderRefusal("process arguments are an argv list of strings")
        for name in self.expected_outputs:
            safe_relative(name)
        names = [f.name for f in self.inputs]
        if len(set(names)) != len(names):
            raise ProviderRefusal("duplicate generated input file names")
        if not float(self.timeout_s) > 0:
            raise ProviderRefusal("a process execution needs a positive timeout")

    def to_dict(self) -> dict[str, Any]:
        # executable PATH is operational; its digest and version are identity
        return {"executable_digest": self.executable_digest, "version": self.version, "args": list(self.args),
                "inputs": [[f.name, f.digest] for f in sorted(self.inputs, key=lambda f: f.name)],
                "environment": [list(x) for x in sorted(self.environment)], "timeout_s": repr(float(self.timeout_s)),
                "expected_outputs": sorted(self.expected_outputs)}

    @property
    def digest(self) -> str:
        return content_digest(self.to_dict())


@dataclass(frozen=True)
class ProcessExecutionRecord:
    invocation_digest: str
    exit_code: int | None
    timed_out: bool
    stdout_digest: str
    stderr_digest: str
    stdout_tail: str
    stderr_tail: str
    outputs: tuple[tuple[str, str, int], ...]   # (name, sha256, size) created/changed by THIS run
    missing_outputs: tuple[str, ...]
    stale_inputs_untouched: tuple[str, ...]     # pre-existing non-input files left unchanged
    duration_s: float
    #: (invocation digest, exit code, timed out) per executed step of a sequence
    steps: tuple[tuple[str, int | None, bool], ...] = ()

    @property
    def completed(self) -> bool:
        """The process ran to exit 0 and produced every expected output (NOT scientific success)."""
        return self.exit_code == 0 and not self.timed_out and not self.missing_outputs

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "process_execution_not_evidence", "invocation_digest": self.invocation_digest,
                "exit_code": self.exit_code, "timed_out": self.timed_out, "stdout_digest": self.stdout_digest,
                "stderr_digest": self.stderr_digest, "outputs": [list(o) for o in self.outputs],
                "missing_outputs": list(self.missing_outputs), "steps": [list(s) for s in self.steps]}

    @property
    def digest(self) -> str:
        return content_digest(self.to_dict())


def _snapshot(root: str) -> dict[str, str]:
    """Digests of regular files; a symlink is recorded as a marker and is never an admissible output."""
    found = {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if os.path.islink(full):
                found[rel] = "symlink:" + os.readlink(full)
                continue
            with open(full, "rb") as fh:
                found[rel] = _sha(fh.read())
    return found


class ProcessWorkspace:
    """A fresh bounded directory for one execution; outputs are read only through digest checks."""

    def __init__(self, root: str | None = None, *, preexisting: Mapping[str, bytes] | None = None) -> None:
        self.path = tempfile.mkdtemp(prefix="forge-proc-", dir=root)
        # ``preexisting`` exists only so tests can prove stale files are refused
        for name, data in (preexisting or {}).items():
            self._write(safe_relative(name), data)
        self.record: ProcessExecutionRecord | None = None

    def _write(self, name: str, data: bytes) -> None:
        full = os.path.join(self.path, *name.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(data)

    def run(self, invocation: ProcessInvocation) -> ProcessExecutionRecord:
        return self.run_sequence((invocation,))

    def run_sequence(self, invocations: tuple[ProcessInvocation, ...]) -> ProcessExecutionRecord:
        """Run a DECLARED sequence of processes in this workspace (e.g. mesh -> solve -> post).

        The sequence stops at the first step that does not exit 0.  Outputs are
        judged against the snapshot taken before the FIRST step, so a file only
        counts if this sequence created or changed it.
        """
        if self.record is not None:
            raise ProviderRefusal("a workspace executes exactly once")
        invocations = tuple(invocations)
        if not invocations:
            raise ProviderRefusal("an empty process sequence")
        inputs: dict[str, bytes] = {}
        for inv in invocations:
            for f in inv.inputs:
                if f.name in inputs and inputs[f.name] != f.content:
                    raise ProviderRefusal(f"two steps declare different contents for input {f.name!r}")
                inputs[f.name] = f.content
        for name, data in inputs.items():
            self._write(name, data)
        before = _snapshot(self.path)
        start = time.perf_counter()
        steps, outs, errs = [], [], []
        exit_code: int | None = 0
        timed_out = False
        for inv in invocations:
            with open(inv.executable, "rb") as fh:
                if _sha(fh.read()) != inv.executable_digest:
                    raise ProviderRefusal(f"executable {inv.executable} changed since discovery; its identity no longer holds")
            proc = subprocess.Popen([inv.executable, *inv.args], cwd=self.path, env=dict(inv.environment), stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, start_new_session=(os.name == "posix"))
            step_timeout = False
            try:
                out, err = proc.communicate(timeout=float(inv.timeout_s))
            except subprocess.TimeoutExpired:
                step_timeout = True
                try:
                    if os.name == "posix":
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                finally:
                    out, err = proc.communicate()
            code = None if step_timeout else proc.returncode
            steps.append((inv.digest, code, step_timeout))
            outs.append(out or b"")
            errs.append(err or b"")
            if step_timeout or code != 0:
                exit_code, timed_out = code, step_timeout
                break
        duration = time.perf_counter() - start
        after = _snapshot(self.path)
        changed = sorted(n for n, d in after.items() if n not in inputs and before.get(n) != d and not d.startswith("symlink:"))
        untouched = sorted(n for n in before if n not in inputs and after.get(n) == before[n])
        outputs = tuple((n, after[n], os.path.getsize(os.path.join(self.path, *n.split("/")))) for n in changed)
        expected = {name for inv in invocations for name in inv.expected_outputs}
        missing = tuple(sorted(expected - set(changed)))
        out_all, err_all = b"\n".join(outs), b"\n".join(errs)
        digest = invocations[0].digest if len(invocations) == 1 else content_digest([inv.to_dict() for inv in invocations])
        self.record = ProcessExecutionRecord(
            digest, exit_code, timed_out, _sha(out_all), _sha(err_all),
            out_all[-TAIL:].decode("utf-8", "replace"), err_all[-TAIL:].decode("utf-8", "replace"),
            outputs, missing, tuple(untouched), duration, tuple(steps))
        return self.record

    def read_output(self, name: str) -> bytes:
        """Bytes of an output THIS execution produced, verified against its recorded digest."""
        if self.record is None:
            raise ProviderRefusal("no execution has run in this workspace")
        name = safe_relative(name)
        recorded = {n: d for n, d, _ in self.record.outputs}
        if name not in recorded:
            reason = "was present before the run and untouched (stale)" if name in self.record.stale_inputs_untouched else \
                "was not produced by this execution"
            raise ProviderRefusal(f"output {name!r} {reason}; it is not admitted as a result")
        with open(os.path.join(self.path, *name.split("/")), "rb") as fh:
            data = fh.read()
        if _sha(data) != recorded[name]:
            raise ProviderRefusal(f"output {name!r} changed after the execution recorded it (foreign content)")
        return data

    def outputs_matching(self, pattern: str) -> tuple[str, ...]:
        rx = re.compile(pattern)
        return tuple(n for n, _, _ in (self.record.outputs if self.record else ()) if rx.fullmatch(n))

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def minimal_environment(executable: str, extra: Mapping[str, str] | None = None) -> tuple[tuple[str, str], ...]:
    """PATH limited to the executable's directory plus declared extras (sorted, exact)."""
    env = {"PATH": os.path.dirname(executable), "HOME": tempfile.gettempdir(), "LC_ALL": "C", "OMP_NUM_THREADS": "1"}
    env.update(dict(extra or {}))
    return tuple(sorted(env.items()))
