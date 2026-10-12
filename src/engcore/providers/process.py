"""Safe boundary for external solver processes.

* argv lists only -- never a shell string; no user-provided shell is executed;
* a fresh, bounded workspace per execution; generated file names are sanitized;
* an explicit, minimal process environment (no inherited environment leakage);
* timeout with termination of the whole child process group;
* stdout/stderr spill to unnamed temporary files, never pipes: memory stays
  bounded whatever a solver prints, and a descendant that escaped termination
  cannot keep the timed-out step blocked by holding a pipe open;
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
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping

from .catalog import ProviderStatus, conda_environment_digest
from .identity import content_digest
from .records import ProviderRefusal

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$")
TAIL = 4000
#: Seconds to wait for a killed step to be reaped. Operational, not scientific:
#: after SIGKILL / ``taskkill /F`` the direct child exits at once; the bound only
#: keeps a platform that never reports its exit from blocking the caller.
REAP_TIMEOUT_S = 10.0
_CHUNK = 1 << 20


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _kill_tree(proc: subprocess.Popen) -> None:
    """Terminate a timed-out step and every descendant it started.

    POSIX: the step leads its own session, so its process group is killed.
    Windows has no process group to signal; ``Popen.kill`` ends only the direct
    child, and a descendant that inherited the output pipes keeps
    ``communicate`` blocked for as long as it lives -- the timeout would then
    bound nothing. ``taskkill /T`` ends the tree; ``kill`` remains as a fallback.
    """
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:  # the whole group exited between the timeout and the kill
            pass
        return
    taskkill = os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32", "taskkill.exe")
    try:
        subprocess.run([taskkill, "/T", "/F", "/PID", str(proc.pid)], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass
    finally:
        proc.kill()


def _exited_within(proc: subprocess.Popen, timeout_s: float) -> bool:
    """Whether the process exits within ``timeout_s``, learnt the moment it does.

    ``Popen.wait(timeout)`` polls on POSIX with a back-off of up to 50 ms, which
    added that much latency to every short solve once output stopped going
    through pipes. A reaper thread blocks in ``wait()`` instead and signals.
    """
    exited = threading.Event()

    def reap() -> None:
        try:
            proc.wait()
        finally:
            exited.set()

    threading.Thread(target=reap, name=f"forge-reap-{proc.pid}", daemon=True).start()
    return exited.wait(timeout_s)


def _stop(proc: subprocess.Popen) -> None:
    """Kill the step's tree and reap the direct child within :data:`REAP_TIMEOUT_S`.

    Not a guarantee that every descendant is gone: one that started its own
    session (POSIX) or was orphaned before the kill (Windows ``taskkill /T``
    follows parent links) can survive. Output goes to files, not pipes, so such
    a survivor cannot hold the caller; it can only keep writing to a file that
    has already been read.
    """
    try:
        _kill_tree(proc)
    finally:
        try:
            proc.wait(timeout=REAP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            pass


def _read_at(fh, offset: int, length: int) -> bytes:
    """Read without moving the file position where the platform allows it.

    An escaped descendant shares the position of the file it inherited; moving
    it back to 0 would make its later writes overwrite what is being read.
    POSIX reads by offset; Windows has no ``pread`` and falls back to seeking.
    """
    if hasattr(os, "pread"):
        return os.pread(fh.fileno(), length, offset)
    fh.seek(offset)
    return fh.read(length)


def _digest_and_tail(streams: list) -> tuple[str, bytes]:
    """sha256 and last :data:`TAIL` bytes of the streams joined by newlines, read in chunks.

    Byte-identical to hashing the newline-joined contents, the form records were always digested in.
    Each stream is read up to the size it had when reading began.
    """
    h = hashlib.sha256()
    tails = []
    for i, fh in enumerate(streams):
        if i:
            h.update(b"\n")
        fh.flush()
        size = os.fstat(fh.fileno()).st_size
        offset = 0
        while offset < size:
            chunk = _read_at(fh, offset, min(_CHUNK, size - offset))
            if not chunk:
                break
            h.update(chunk)
            offset += len(chunk)
        tails.append(_read_at(fh, max(0, offset - TAIL), min(TAIL, offset)))
    return h.hexdigest(), b"\n".join(tails)[-TAIL:]


def run_bounded(argv: list[str] | tuple[str, ...], *, timeout_s: float, input_bytes: bytes | None = None,
                env: Mapping[str, str] | None = None, cwd: str | None = None,
                max_output_bytes: int | None = None) -> tuple[int | None, bool, bytes, bytes]:
    """Run one process under the workspace's termination and capture rules: ``(exit, timed_out, stdout, stderr)``.

    For launches that need no workspace (a JSON-in/JSON-out runner). Output is
    spilled to temporary files while the process runs and read back whole after
    it ends, so memory is bounded only by ``max_output_bytes`` (caller-declared,
    none by default), which refuses a larger stream instead of loading it.
    ``exit`` is ``None`` on a timeout. A launch failure is a :class:`ProviderRefusal`.
    """
    if not float(timeout_s) > 0:
        raise ProviderRefusal("a process execution needs a positive timeout")
    argv = list(argv)
    with tempfile.TemporaryFile() as stdin_f, tempfile.TemporaryFile() as out_f, tempfile.TemporaryFile() as err_f:
        if input_bytes is not None:
            stdin_f.write(input_bytes)
            stdin_f.seek(0)
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=None if env is None else dict(env),
                                    stdin=stdin_f if input_bytes is not None else subprocess.DEVNULL,
                                    stdout=out_f, stderr=err_f, start_new_session=(os.name == "posix"))
        except OSError as exc:
            raise ProviderRefusal(f"could not launch {argv[0] if argv else '<empty argv>'}: {exc}") from exc
        try:
            timed_out = not _exited_within(proc, float(timeout_s))
        except BaseException:  # an interrupt must not leave the process running
            _stop(proc)
            raise
        if timed_out:
            _stop(proc)
        streams = []
        for fh in (out_f, err_f):
            size = os.fstat(fh.fileno()).st_size
            if max_output_bytes is not None and size > max_output_bytes:
                raise ProviderRefusal(f"{argv[0]} wrote {size} bytes to one stream, more than the declared "
                                      f"{max_output_bytes}; the output is refused, not truncated")
            streams.append(_read_at(fh, 0, size))
        return (None if timed_out else proc.returncode), timed_out, streams[0], streams[1]


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
    #: (prefix, sha256 of its package set at discovery) for an executable that runs from a conda
    #: environment. Operational, not identity (the execution identity already binds the digest):
    #: a launch recomputes it and refuses a changed environment. See :func:`conda_environment_of`.
    conda_environment: tuple[str, str] | tuple[()] = ()

    def __post_init__(self) -> None:
        if not os.path.isabs(self.executable):
            raise ProviderRefusal("the executable must be an exact absolute path from provider discovery")
        if self.conda_environment:
            prefix, digest = self.conda_environment
            if not os.path.isabs(prefix) or not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
                raise ProviderRefusal("a conda environment check needs an absolute prefix and its sha256 package-set digest")
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
        if self.record is not None or getattr(self, "_started", False):
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
        # spent from here on: a refusal at a later step's launch check must not leave a workspace that could run again
        self._started = True
        steps, outs, errs = [], [], []
        exit_code: int | None = 0
        timed_out = False
        try:
            self._run_steps(invocations, steps, outs, errs)
            for _, code, step_timeout in steps:
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
            out_digest, out_tail = _digest_and_tail(outs)
            err_digest, err_tail = _digest_and_tail(errs)
        finally:
            for fh in (*outs, *errs):
                fh.close()
        digest = invocations[0].digest if len(invocations) == 1 else content_digest([inv.to_dict() for inv in invocations])
        self.record = ProcessExecutionRecord(
            digest, exit_code, timed_out, out_digest, err_digest,
            out_tail.decode("utf-8", "replace"), err_tail.decode("utf-8", "replace"),
            outputs, missing, tuple(untouched), duration, tuple(steps))
        return self.record

    def _run_steps(self, invocations: tuple[ProcessInvocation, ...], steps: list, outs: list, errs: list) -> None:
        """Run the declared steps in order and stop at the first that does not exit 0.

        Each step's stdout/stderr go to its own temporary file, appended to
        ``outs`` / ``errs`` before launch so the caller always closes them.
        """
        for inv in invocations:
            with open(inv.executable, "rb") as fh:
                if _sha(fh.read()) != inv.executable_digest:
                    raise ProviderRefusal(f"executable {inv.executable} changed since discovery; its identity no longer holds")
            if inv.conda_environment:
                prefix, expected = inv.conda_environment
                try:
                    actual, _ = conda_environment_digest(prefix)
                except (OSError, ValueError, AttributeError) as exc:  # unreadable / non-JSON / non-object records
                    raise ProviderRefusal(f"the environment {prefix} cannot be re-read at launch: {exc}") from exc
                if actual != expected:
                    raise ProviderRefusal(f"environment {prefix} changed since discovery (package set {actual[:12]} != {expected[:12]}); "
                                          "the execution identity no longer describes what would run")
            out_f, err_f = tempfile.TemporaryFile(), tempfile.TemporaryFile()
            outs.append(out_f)
            errs.append(err_f)
            try:
                proc = subprocess.Popen([inv.executable, *inv.args], cwd=self.path, env=dict(inv.environment), stdout=out_f,
                                        stderr=err_f, stdin=subprocess.DEVNULL, start_new_session=(os.name == "posix"))
            except OSError as exc:  # exec format error, permission denied: no process ran
                raise ProviderRefusal(f"could not launch {inv.executable}: {exc}") from exc
            try:
                step_timeout = not _exited_within(proc, float(inv.timeout_s))
            except BaseException:  # an interrupt must not leave the step running
                _stop(proc)
                raise
            if step_timeout:
                _stop(proc)
            code = None if step_timeout else proc.returncode
            steps.append((inv.digest, code, step_timeout))
            if step_timeout or code != 0:
                return

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


def conda_environment_of(status: ProviderStatus) -> tuple[str, str] | tuple[()]:
    """The launch-time environment check for a process provider discovered in a conda environment.

    ``()`` when discovery bound no conda environment. Otherwise the prefix the
    executable runs from (``<prefix>/bin/<exe>``) and the package-set digest
    discovery recorded; the prefix must actually be a conda environment.
    """
    digests = [d for name, _, d in status.dependencies if name == "conda-environment"]
    if not digests:
        return ()
    prefix = os.path.dirname(os.path.dirname(status.location))
    if not os.path.isdir(os.path.join(prefix, "conda-meta")):
        raise ProviderRefusal(f"{status.location} was discovered with a conda environment, but {prefix} is not one")
    return (prefix, digests[0])


def minimal_environment(executable: str, extra: Mapping[str, str] | None = None) -> tuple[tuple[str, str], ...]:
    """PATH limited to the executable's directory plus declared extras (sorted, exact)."""
    env = {"PATH": os.path.dirname(executable), "HOME": tempfile.gettempdir(), "LC_ALL": "C", "OMP_NUM_THREADS": "1"}
    env.update(dict(extra or {}))
    return tuple(sorted(env.items()))
