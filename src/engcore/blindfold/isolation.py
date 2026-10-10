"""An isolated Blindfold deployment: the Escrow and the Discovery runtime in DIFFERENT security domains.

::

    DISCOVERY PROCESS (uid 65534, no capabilities, no_new_privs,          ESCROW PROCESS (escrow uid)
      private mount / pid / net / ipc / uts namespaces,                      + private storage (0700):
      no network but loopback, the escrow storage path                         master secret, signing key,
      over-mounted with an empty tmpfs)                                        keyed journal
            |                                                                       ^
            +------------- one inherited UNIX socket (the protocol, nothing else) --+

The Discovery side receives exactly what a proposer may have: its campaign id, its OBSERVE capability, the public
cards and the escrow's PUBLIC key.  It never holds the operator credential, the score capability, a seed, a law, an
evaluation point, the truth volume or an environment variable carrying any of them.

What this proves, and what it does not (:data:`BOUNDARY_LEVELS`):

* ``PROTOCOL_SECURITY_VERIFIED`` -- the protocol attack tests pass inside ONE security domain (``tests/foundations/
  test_escrow_boundary.py``): authenticated requests, single-use query ids, signed responses, persisted budgets.
* ``OS_ISOLATION_BOUNDARY_VERIFIED`` -- :func:`run_isolation_demo` ran a hostile proposer under a separate uid in
  private namespaces and every attack failed (truth path, traversal, environment, other processes, network, protocol
  substitution / replay / over-querying), and none of the escrow's secret, key or journal bytes were readable to it.
  Same kernel and same container as the escrow: a kernel or container escape is out of scope.
* ``CONTAINER_BOUNDARY_VERIFIED`` / ``HOST_BOUNDARY_VERIFIED`` -- NOT reached here (no container runtime daemon, no
  second host in this environment).  Nothing in this module claims them.

The escrow's own responses keep saying what the escrow can know about its deployment
(``SECURITY_BOUNDARY_NOT_PROVEN`` unless the launcher states the verified level it established).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
from typing import Any

from .escrow import SECURITY_LABEL, EscrowStorage, OperatorClient, ScoreClient

BOUNDARY_LEVELS = ("SECURITY_BOUNDARY_NOT_PROVEN", "PROTOCOL_SECURITY_VERIFIED", "OS_ISOLATION_BOUNDARY_VERIFIED",
                   "CONTAINER_BOUNDARY_VERIFIED", "HOST_BOUNDARY_VERIFIED")
DISCOVERY_UID = 65534
_MECHANISM = ("separate uid 65534 (setpriv --reuid/--regid, cleared groups, all capabilities dropped from inheritable and "
              "bounding sets, no_new_privs); private mount, pid (with its own /proc), network, ipc and uts namespaces "
              "(unshare); the escrow storage path over-mounted with an empty tmpfs; escrow storage 0700 owned by the escrow uid; "
              "the only channel an inherited AF_UNIX socket")


def isolation_support() -> tuple[bool, str]:
    """Whether this host can build the isolated deployment (root to create namespaces and switch uid, the tools)."""
    if os.geteuid() != 0:
        return False, "creating the namespaces and switching to the discovery uid needs root on the launcher side"
    missing = [t for t in ("unshare", "setpriv", "mount") if shutil.which(t) is None]
    if missing:
        return False, f"missing tools: {missing}"
    probe = subprocess.run(["unshare", "--mount", "--pid", "--fork", "--net", "--mount-proc", "--", sys.executable, "-c", "pass"],
                           capture_output=True, timeout=30)
    if probe.returncode != 0:
        return False, f"the kernel refused the namespaces: {probe.stderr.decode()[:160]}"
    return True, "ok"


class IsolatedEscrow:
    """The escrow process with its private storage, and launchers for Discovery processes in another domain."""

    def __init__(self, storage_dir: str | os.PathLike[str], *, boundary_label: str = SECURITY_LABEL) -> None:
        ok, why = isolation_support()
        if not ok:
            raise RuntimeError(f"isolated deployment unavailable: {why}")
        self.storage_dir = pathlib.Path(storage_dir).resolve()
        EscrowStorage(self.storage_dir, create=True)             # creates and checks the private storage (0700, 0600)
        self._label = boundary_label
        self._proc: subprocess.Popen | None = None
        self.start()

    def start(self) -> None:
        self._escrow_end, self._discovery_end = socket.socketpair()
        env = {"PATH": "/usr/bin:/bin"}
        self._proc = subprocess.Popen([sys.executable, "-I", "-m", "engcore.blindfold.escrow_server", "--storage", str(self.storage_dir),
                                       "--fd", str(self._escrow_end.fileno()), "--boundary", self._label],
                                      pass_fds=(self._escrow_end.fileno(),), stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, env=env)
        self._escrow_end.close()                                 # the escrow process holds its end; the launcher does not
        hello = json.loads(self._proc.stdout.readline() or b"{}")  # type: ignore[union-attr]
        self.operator_token, self.escrow_public = hello["operator_token"], hello["escrow_public"]
        self._r, self._w = self._discovery_end.makefile("rb"), self._discovery_end.makefile("wb")

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            self._proc.wait(timeout=10)
        self._discovery_end.close()

    def restart(self) -> None:
        self.stop()
        self.start()

    def __call__(self, request: bytes) -> bytes:                # the OPERATOR / EVALUATOR side's transport (launcher domain)
        self._w.write(request.replace(b"\n", b" ") + b"\n")
        self._w.flush()
        return self._r.readline()

    def run_discovery(self, task: dict[str, Any], *, timeout: float = 300) -> dict[str, Any]:
        """Run the hostile proposer (:mod:`.isolation_probe`) in the Discovery domain; return its report."""
        pydir = pathlib.Path(sys.executable).resolve().parent.parent
        src = pathlib.Path(__file__).resolve().parents[2]
        site = next(p for p in sys.path if p.endswith("site-packages") and os.path.isdir(p))
        fd = self._discovery_end.fileno()
        boot = (f"import sys; sys.path[:0] = [{str(src)!r}, {site!r}]\n"
                "from engcore.blindfold.isolation_probe import main; raise SystemExit(main())\n")
        inner = (f"mkdir -p /mnt/fpy && mount --bind {_q(pydir)} /mnt/fpy && "
                 f"mount -t tmpfs -o size=64k,mode=000 tmpfs {_q(self.storage_dir)} && "
                 f"exec setpriv --reuid={DISCOVERY_UID} --regid={DISCOVERY_UID} --clear-groups --inh-caps=-all --bounding-set=-all "
                 f"--no-new-privs -- /mnt/fpy/bin/{pathlib.Path(sys.executable).resolve().name} -I -c {_q(boot)}")
        cmd = ["unshare", "--mount", "--pid", "--fork", "--net", "--ipc", "--uts", "--mount-proc", "--", "/bin/sh", "-c", inner]
        out = subprocess.run(cmd, input=json.dumps({**task, "fd": fd}).encode(), capture_output=True, pass_fds=(fd,),
                             env={"PATH": "/usr/bin:/bin"}, cwd="/", timeout=timeout)
        if out.returncode != 0:
            raise RuntimeError(f"discovery process failed: {out.stderr.decode()[-600:]}")
        return json.loads(out.stdout)


def _q(s: Any) -> str:
    import shlex
    return shlex.quote(str(s))


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_isolation_demo(workdir: str | os.PathLike[str]) -> dict[str, Any]:
    """Build the isolated deployment, attack it from the Discovery side twice (with an escrow restart in between),
    and report the security level actually established.  Never claims more than OS_ISOLATION_BOUNDARY_VERIFIED."""
    ok, why = isolation_support()
    if not ok:
        return {"security_boundary_status": "SECURITY_BOUNDARY_NOT_PROVEN", "isolation_available": False, "reason": why}
    work = pathlib.Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    escrow = IsolatedEscrow(work / "escrow-truth")
    try:
        op = OperatorClient(escrow, escrow.operator_token, escrow_public=escrow.escrow_public)
        cfg = "b" * 64
        mine = op.create("iso-1", {"discoverable": 2}, evaluator_config_digest=cfg)
        other = op.create("iso-other", {"discoverable": 1}, evaluator_config_digest=cfg)
        store = escrow.storage_dir
        truth_paths = [str(store / "escrow.secret"), str(store / "escrow.ed25519.pem"), str(store / "journal.jsonl")]
        task = {"campaign_id": "iso-1", "observe_token": mine["tokens"]["observe"], "escrow_public": escrow.escrow_public,
                "cards": mine["cards"], "truth_paths": truth_paths, "other_campaign_id": "iso-other",
                "other_universe_id": other["cards"][0]["universe_id"]}
        run1 = escrow.run_discovery({**task, "run": 1})
        spent_before = op.log("iso-1")["spent"]
        escrow.restart()                                          # ESCROW restart: state from the journal
        op = OperatorClient(escrow, escrow.operator_token, escrow_public=escrow.escrow_public)
        spent_after = op.log("iso-1")["spent"]
        sc = ScoreClient(escrow, "iso-1", mine["tokens"]["score"], escrow_public=escrow.escrow_public)
        sc.score(mine["cards"][1]["universe_id"], {"answer": "no_law"})
        escrow.restart()
        sc = ScoreClient(escrow, "iso-1", mine["tokens"]["score"], escrow_public=escrow.escrow_public)
        try:
            sc.score(mine["cards"][1]["universe_id"], {"answer": "no_law"})
            second_submission_refused = False
        except Exception:                                         # noqa: BLE001 - the refusal is the expected outcome
            second_submission_refused = True
        run2 = escrow.run_discovery({**task, "run": 2})            # DISCOVERY restart: a fresh process, same capability
        secret_digests = {name: _sha256_file(store / name) for name in ("escrow.secret", "escrow.ed25519.pem", "journal.jsonl")}
    finally:
        escrow.stop()
    attacks_succeeded = sorted({f"run{n}:{k}" for n, r in ((1, run1), (2, run2)) for k, v in r["attacks"].items() if v["succeeded"]})
    leaked = sorted(name for name, d in secret_digests.items() if d in set(run1["readable_file_digests"]) | set(run2["readable_file_digests"]))
    checks = {
        "discovery_uid_is_unprivileged": run1["uid"] == run1["euid"] == DISCOVERY_UID,
        "no_attack_succeeded": not attacks_succeeded,
        "no_escrow_secret_readable": not leaked,
        "only_loopback_network": run1["network_interfaces"] == ["lo"],
        # its own pid namespace: only the namespace's first processes (sh -> setpriv -> python) are visible, no escrow
        "escrow_process_invisible": max(run1["visible_pids"]) <= 3 and max(run2["visible_pids"]) <= 3,
        "no_hidden_fields_in_responses": not run1.get("response_leaks_hidden_fields", True),
        "budget_persisted_across_escrow_restart": spent_before == spent_after and any(v > 0 for v in spent_after.values()),
        "second_sealed_submission_refused_after_restart": second_submission_refused,
        "discovery_restart_does_not_reset_budget": "first_observation_refused" in run2
        or run2.get("first_observation_budget_remaining", 1e9) < run1.get("first_observation_budget_remaining", 0),
    }
    status = "OS_ISOLATION_BOUNDARY_VERIFIED" if all(checks.values()) else "SECURITY_BOUNDARY_NOT_PROVEN"
    return {"security_boundary_status": status, "isolation_available": True, "mechanism": _MECHANISM, "checks": checks,
            "attacks_succeeded": attacks_succeeded, "secrets_readable": leaked,
            "attacks_run": sorted(run1["attacks"]), "files_scanned_by_discovery": [run1["files_scanned"], run2["files_scanned"]],
            "not_established": ["CONTAINER_BOUNDARY_VERIFIED (no container runtime daemon here)",
                                "HOST_BOUNDARY_VERIFIED (single host)", "kernel / container escape resistance"]}


__all__ = ["BOUNDARY_LEVELS", "DISCOVERY_UID", "IsolatedEscrow", "isolation_support", "run_isolation_demo"]
