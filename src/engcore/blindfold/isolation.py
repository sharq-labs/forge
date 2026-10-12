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
  private namespaces, twice (with an escrow restart in between), and:
  - the LAUNCHER verified each Discovery process from outside, through /proc: uid / gid 65534 with no groups, every
    capability set empty, no_new_privs, its own mount / pid / net / ipc / uts namespaces, and a tmpfs over the escrow
    storage path in its mount table;
  - every attack failed (truth path, traversal, environment, other processes, network, protocol substitution / replay /
    over-querying), no response it received carried a hidden-world key, and the refusals named no hidden field;
  - the escrow's canary (written into its journal at creation) appeared in NO file it could read, and no readable file
    matched the secret, key or journal; the detector itself is shown to work by a positive control
    (``leak_control=True`` plants a readable copy and must yield NOT_PROVEN).
  The record is bound to the escrow's key id and to digests of the mechanism and the checks.  Same kernel and same
  container as the escrow: a kernel or container escape is out of scope.  The LAUNCHER (operator / evaluator) runs as
  root in the escrow's domain and can read its storage: only Discovery is isolated.
* ``CONTAINER_BOUNDARY_VERIFIED`` / ``HOST_BOUNDARY_VERIFIED`` -- NOT reached here (no container runtime daemon, no
  second host in this environment).  Nothing in this module claims them.

The escrow's own responses always say ``SECURITY_BOUNDARY_NOT_PROVEN``: the verified level is this demo's record, bound
to the escrow key id it was established for, never a flag the escrow (or its launcher) can set.
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
from collections.abc import Mapping
from typing import Any

from .escrow import (
    EscrowCheckpoint,
    EscrowRefused,
    EscrowStorage,
    OperatorClient,
    ScoreClient,
)

BOUNDARY_LEVELS = ("SECURITY_BOUNDARY_NOT_PROVEN", "PROTOCOL_SECURITY_VERIFIED", "OS_ISOLATION_BOUNDARY_VERIFIED",
                   "CONTAINER_BOUNDARY_VERIFIED", "HOST_BOUNDARY_VERIFIED")
DISCOVERY_UID = 65534
_MECHANISM = ("separate uid 65534 (setpriv --reuid/--regid, cleared groups, all capabilities dropped from inheritable and "
              "bounding sets, no_new_privs); private mount, pid (with its own /proc), network, ipc and uts namespaces "
              "(unshare); the escrow storage path over-mounted with an empty tmpfs; escrow storage 0700 owned by the escrow uid; "
              "the only channel an inherited AF_UNIX socket.  The launcher (operator / evaluator) runs as root in the escrow's "
              "domain: only Discovery is isolated")


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

    def __init__(self, storage_dir: str | os.PathLike[str]) -> None:
        ok, why = isolation_support()
        if not ok:
            raise RuntimeError(f"isolated deployment unavailable: {why}")
        self.storage_dir = pathlib.Path(storage_dir).resolve()
        st = EscrowStorage(self.storage_dir, create=True)        # creates and checks the private storage (0700, 0600)
        self.canary = st.canary
        self.created_at = (self.storage_dir / "journal.jsonl").stat().st_mtime
        self._proc: subprocess.Popen | None = None
        self.start()

    def start(self) -> None:
        self._escrow_end, self._discovery_end = socket.socketpair()
        env = {"PATH": "/usr/bin:/bin"}
        self._proc = subprocess.Popen([sys.executable, "-I", "-m", "engcore.blindfold.escrow_server", "--storage", str(self.storage_dir),
                                       "--fd", str(self._escrow_end.fileno())],
                                      pass_fds=(self._escrow_end.fileno(),), stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, env=env)
        self._escrow_end.close()                                 # the escrow process holds its end; the launcher does not
        hello = json.loads(self._proc.stdout.readline() or b"{}")  # type: ignore[union-attr]
        self.operator_token, self.escrow_public = hello["operator_token"], hello["escrow_public"]
        self._r, self._w = self._discovery_end.makefile("rb"), self._discovery_end.makefile("wb")

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:  # ignored SIGTERM: it must not outlive stop()
                self._proc.kill()
                self._proc.wait(timeout=10)
        self._discovery_end.close()

    def restart(self) -> None:
        self.stop()
        self.start()

    def __call__(self, request: bytes) -> bytes:                # the OPERATOR / EVALUATOR side's transport (launcher domain)
        self._w.write(request.replace(b"\n", b" ") + b"\n")
        self._w.flush()
        return self._r.readline()

    def run_discovery(self, task: dict[str, Any], *, timeout: float = 300) -> tuple[dict[str, Any], dict[str, Any]]:
        """Run the hostile proposer (:mod:`.isolation_probe`) in the Discovery domain.  Returns (its report, what the
        LAUNCHER verified about the process from outside, through /proc, before letting it run)."""
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
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(fd,),
                                env={"PATH": "/usr/bin:/bin"}, cwd="/")
        assert proc.stdin is not None and proc.stdout is not None
        try:
            proc.stdin.write((json.dumps({**task, "fd": fd}) + "\n").encode())
            proc.stdin.flush()
            ready = json.loads(proc.stdout.readline() or b"{}")
            outside = _inspect(_leaf(proc.pid), self.storage_dir) if ready.get("ready") else {"inspected": False}
            proc.stdin.write(b"go\n")
            proc.stdin.close()
            out, err = proc.stdout.read(), proc.stderr.read() if proc.stderr else b""
            proc.wait(timeout=timeout)
        finally:
            if proc.poll() is None:
                proc.kill()
        if proc.returncode != 0:
            raise RuntimeError(f"discovery process failed: {err.decode()[-600:]}")
        return json.loads(out), outside


def _leaf(pid: int) -> int:
    """The deepest descendant of ``pid`` (unshare -> sh -> python after exec)."""
    while True:
        try:
            kids = [int(k) for t in os.listdir(f"/proc/{pid}/task") for k in open(f"/proc/{pid}/task/{t}/children").read().split()]
        except OSError:
            return pid
        if not kids:
            return pid
        pid = kids[-1]


def _inspect(pid: int, storage_dir: pathlib.Path) -> dict[str, Any]:
    """What the launcher sees of the Discovery process from OUTSIDE its domain (never the process's own report)."""
    status = dict(line.split(":", 1) for line in open(f"/proc/{pid}/status").read().splitlines() if ":" in line)
    ids = lambda k: [int(x) for x in status.get(k, "").split()]
    caps = {k: int(status.get(k, "f").strip() or "f", 16) for k in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")}
    ns = {n: os.readlink(f"/proc/{pid}/ns/{n}") != os.readlink(f"/proc/self/ns/{n}") for n in ("mnt", "pid", "net", "ipc", "uts")}
    mounts = [ln.split() for ln in open(f"/proc/{pid}/mountinfo").read().splitlines()]
    tmpfs_over = any(m[4] == str(storage_dir) and m[m.index("-") + 1] == "tmpfs" for m in mounts if "-" in m)
    return {"inspected": True, "uid": ids("Uid"), "gid": ids("Gid"), "groups": ids("Groups"), "caps": caps,
            "no_new_privs": status.get("NoNewPrivs", "").strip() == "1", "private_namespaces": ns, "tmpfs_over_storage": tmpfs_over}


def _outside_ok(o: Mapping[str, Any]) -> bool:
    return bool(o.get("inspected") and o["uid"] == [DISCOVERY_UID] * 4 and o["gid"] == [DISCOVERY_UID] * 4 and not o["groups"]
                and not any(o["caps"].values()) and o["no_new_privs"] and all(o["private_namespaces"].values())
                and o["tmpfs_over_storage"])


def _q(s: Any) -> str:
    import shlex
    return shlex.quote(str(s))


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def run_isolation_demo(workdir: str | os.PathLike[str], *, leak_control: bool = False) -> dict[str, Any]:
    """Build the isolated deployment, attack it from the Discovery side twice (with an escrow restart in between),
    and report the security level actually established.  Never claims more than OS_ISOLATION_BOUNDARY_VERIFIED.

    ``leak_control``: the POSITIVE CONTROL -- a world-readable copy of the journal is planted where Discovery can read
    it; the leak detector must catch it and the status must be NOT_PROVEN (otherwise the detector proves nothing)."""
    ok, why = isolation_support()
    if not ok:
        return {"security_boundary_status": "SECURITY_BOUNDARY_NOT_PROVEN", "isolation_available": False, "reason": why}
    work = pathlib.Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    escrow = IsolatedEscrow(work / "escrow-truth")
    planted: pathlib.Path | None = None
    try:
        ck = EscrowCheckpoint(work / "operator.checkpoint")        # the launcher's OWN checkpoint (rollback detection)
        op = OperatorClient(escrow, escrow.operator_token, escrow_public=escrow.escrow_public, checkpoint=ck)
        cfg = "b" * 64
        mine = op.create("iso-1", {"discoverable": 2}, evaluator_config_digest=cfg)
        other = op.create("iso-other", {"discoverable": 1}, evaluator_config_digest=cfg)
        store = escrow.storage_dir
        if leak_control:
            import tempfile
            planted = pathlib.Path(tempfile.mkdtemp(prefix="forge-leak-control-", dir="/tmp"))
            planted.chmod(0o755)
            (planted / "journal.copy").write_bytes((store / "journal.jsonl").read_bytes()[:4096])   # a PARTIAL copy
            (planted / "journal.copy").chmod(0o644)
        truth_paths = [str(store / "escrow.secret"), str(store / "escrow.ed25519.pem"), str(store / "journal.jsonl")]
        task = {"campaign_id": "iso-1", "observe_token": mine["tokens"]["observe"], "escrow_public": escrow.escrow_public,
                "cards": mine["cards"], "truth_paths": truth_paths, "other_campaign_id": "iso-other",
                "other_universe_id": other["cards"][0]["universe_id"], "canary": escrow.canary, "since": escrow.created_at - 2}
        run1, out1 = escrow.run_discovery({**task, "run": 1})
        spent_before = op.log("iso-1")["spent"]
        escrow.restart()                                          # ESCROW restart: state from the journal
        op = OperatorClient(escrow, escrow.operator_token, escrow_public=escrow.escrow_public, checkpoint=ck)
        spent_after = op.log("iso-1")["spent"]
        sc = ScoreClient(escrow, "iso-1", mine["tokens"]["score"], escrow_public=escrow.escrow_public, checkpoint=ck)
        sc.score(mine["cards"][1]["universe_id"], {"answer": "no_law"})
        escrow.restart()
        sc = ScoreClient(escrow, "iso-1", mine["tokens"]["score"], escrow_public=escrow.escrow_public, checkpoint=ck)
        try:
            sc.score(mine["cards"][1]["universe_id"], {"answer": "no_law"})
            second_refusal = ""
        except EscrowRefused as exc:                              # a SIGNED, verified refusal -- an integrity error is not one
            second_refusal = str(exc)
        run2, out2 = escrow.run_discovery({**task, "run": 2})      # DISCOVERY restart: a fresh process, same capability
        secret_digests = {name: _sha256_file(store / name) for name in ("escrow.secret", "escrow.ed25519.pem", "journal.jsonl")}
        key_id = hashlib.sha256(bytes.fromhex(escrow.escrow_public)).hexdigest()
    finally:
        escrow.stop()
        if planted is not None:
            shutil.rmtree(planted, ignore_errors=True)
    runs = ((1, run1), (2, run2))
    attacks_succeeded = sorted({f"run{n}:{k}" for n, r in runs for k, v in r["attacks"].items() if v["succeeded"]})
    readable = set(run1["leak_scan"]["recent_digests"]) | set(run2["leak_scan"]["recent_digests"])
    leaked = sorted({name for name, d in secret_digests.items() if d in readable}
                    | {f"canary in {p}" for _n, r in runs for p in r["leak_scan"]["canary_hits"]})
    checks = {
        "launcher_verified_discovery_domain_run1": _outside_ok(out1),
        "launcher_verified_discovery_domain_run2": _outside_ok(out2),
        "discovery_uid_is_unprivileged": all(r["uid"] == r["euid"] == DISCOVERY_UID for _n, r in runs),
        "no_attack_succeeded": not attacks_succeeded,
        "no_escrow_secret_readable": not leaked,
        "only_loopback_network": all(r["network_interfaces"] == ["lo"] for _n, r in runs),
        # its own pid namespace: only the namespace's first processes (sh -> setpriv -> python) are visible, no escrow
        "escrow_process_invisible": all(max(r["visible_pids"]) <= 3 for _n, r in runs),
        "no_hidden_fields_in_responses": all(not r["response_hidden_keys"] and not r["refusal_mentions_hidden"]
                                             and r["responses_inspected"] > 5 for _n, r in runs),
        "budget_persisted_across_escrow_restart": spent_before == spent_after and any(v > 0 for v in spent_after.values()),
        "second_sealed_submission_refused_after_restart": "one sealed submission" in second_refusal,
        "discovery_restart_does_not_reset_budget": "exhausted" in run2.get("first_observation_refused", "")
        or run2.get("first_observation_budget_remaining", 1e9) < run1.get("first_observation_budget_remaining", 0),
    }
    status = "OS_ISOLATION_BOUNDARY_VERIFIED" if all(checks.values()) else "SECURITY_BOUNDARY_NOT_PROVEN"
    return {"security_boundary_status": status, "isolation_available": True, "leak_control": leak_control,
            "escrow_key_id": key_id, "mechanism": _MECHANISM, "mechanism_digest": _digest(_MECHANISM),
            "checks": checks, "checks_digest": _digest(checks), "launcher_view": {"run1": out1, "run2": out2},
            "attacks_succeeded": attacks_succeeded, "secrets_readable": leaked, "attacks_run": sorted(run1["attacks"]),
            "files_scanned_by_discovery": [r["leak_scan"]["files_stat"] for _n, r in runs],
            "files_read_by_discovery": [r["leak_scan"]["files_read"] for _n, r in runs],
            "not_established": ["CONTAINER_BOUNDARY_VERIFIED (no container runtime daemon here)",
                                "HOST_BOUNDARY_VERIFIED (single host)", "kernel / container escape resistance",
                                "isolation of the launcher (operator / evaluator run as root in the escrow's domain)"]}


__all__ = ["BOUNDARY_LEVELS", "DISCOVERY_UID", "IsolatedEscrow", "isolation_support", "run_isolation_demo"]
