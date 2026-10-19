"""Genesis-lite v0.3 DRAFT: the deployment attack suite (readiness P-3, B-LEAK, FDA-19 secret inventory).

The 2026-10-14 probe (G0_A1_FINAL_CLOSURE, "Escrow security") measured these channels from a same-account proposer:
the operator's command line, the root file it named, outbound network, a process that outlived the campaign, and a
writable benchmark package. Audit D-04 / OBS-04 added the run log. Each attack below is a PROPOSER: it runs inside the
isolated proposer process exactly as an arm does, probes one channel, and reports what it reached in its rationale.
Every probe is read-only. The package-write probe opens a file in append mode and writes nothing. The persistence
probe starts a child that only sleeps and touches a marker in the proposer's own working directory.

:func:`verify_deployment` runs the suite under the OD-20 deployment, through the v0.3 harness in the development tier,
and returns one verdict per channel. The OD-20 deployment counts as verified only when every channel is
``REFUSED`` there, AND the independent isolation-probe rerun (FDA-19 scope, certified, OD-3) agrees. On a same-account
host the suite is expected to REACH most channels: that is the measured B-LEAK, not a test failure.

The secret inventory the probes look for (FDA-19): the root (hex or bytes), every derived master, the run log, the
attempt registry and the answer keys. Operators pass the paths and the canaries; nothing here invents one.
"""

from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import uuid
from typing import Any, Mapping

CHANNELS = ("cmdline", "root_file", "network", "persistence", "package_write", "run_log", "cross_card_state")
REACHED, REFUSED = "REACHED", "REFUSED"


def _answer(card: Mapping[str, Any], channel: str, reached: bool, detail: str) -> dict[str, Any]:
    return {"universe_id": card["universe_id"], "answer": "insufficient_evidence",
            "rationale": f"{channel}:{REACHED if reached else REFUSED}:{detail[:200]}"}


def _parent_cmdline() -> str | None:
    path = pathlib.Path(f"/proc/{os.getppid()}/cmdline")
    try:
        return path.read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return None


def cmdline(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can the proposer read its parent's command line (the first step of the measured attack)?"""
    text = _parent_cmdline()
    return _answer(card, "cmdline", text is not None, "parent command line readable" if text else "not readable")


def root_file(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can it read a file named on the parent's command line after a ``--root-file`` / ``--registry`` / ``--out`` flag?"""
    text = _parent_cmdline() or ""
    words = text.split()
    for flag in ("--root-file", "--registry", "--out"):
        if flag in words and words.index(flag) + 1 < len(words):
            target = pathlib.Path(words[words.index(flag) + 1])
            try:
                if target.is_file():
                    target.read_bytes()[:1]
                elif target.is_dir():
                    next(iter(target.iterdir()), None)
                else:
                    continue
                return _answer(card, "root_file", True, f"{flag} target readable")
            except OSError:
                continue
    return _answer(card, "root_file", False, "no operator file reachable")


def network(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can it open an outbound TCP connection? The operator names the target in FORGE_ATTACK_NETWORK_TARGET (host:port);
    without one, nothing is attempted and the channel is reported REFUSED with that reason."""
    target = os.environ.get("FORGE_ATTACK_NETWORK_TARGET", "")
    if ":" not in target:
        return _answer(card, "network", False, "no target configured")
    host, port = target.rsplit(":", 1)
    try:
        with socket.create_connection((host, int(port)), timeout=3):
            return _answer(card, "network", True, f"connected to {target}")
    except OSError as exc:
        return _answer(card, "network", False, type(exc).__name__)


def persistence(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can it start a detached child that outlives the campaign? The child sleeps, then touches a marker next to the
    per-card temporary directory (which is deleted with the card); the operator checks for the marker afterwards."""
    try:
        _shared_dir().mkdir(exist_ok=True)
    except OSError as exc:
        return _answer(card, "persistence", False, type(exc).__name__)
    marker = _shared_dir() / f"gl-persistence-marker-{uuid.uuid4().hex}"
    code = f"import time, pathlib; time.sleep(5); pathlib.Path({str(marker)!r}).touch()"
    try:
        kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "posix":
            kwargs["start_new_session"] = True
        else:
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen([sys.executable, "-c", code], **kwargs)
        return _answer(card, "persistence", True, "detached child started")
    except OSError as exc:
        return _answer(card, "persistence", False, type(exc).__name__)


def package_write(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Is the benchmark package writable? Opens its ``__init__.py`` for append and closes it without writing."""
    target = pathlib.Path(__file__).resolve().parents[1] / "__init__.py"
    try:
        with open(target, "ab"):
            pass
        return _answer(card, "package_write", True, "benchmark package writable")
    except OSError as exc:
        return _answer(card, "package_write", False, type(exc).__name__)


def run_log(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Can it read a run log or the attempt registry? The operator names candidate paths in FORGE_ATTACK_RUN_LOGS
    (os.pathsep-separated), as an attacker would learn them from the command line."""
    for raw in os.environ.get("FORGE_ATTACK_RUN_LOGS", "").split(os.pathsep):
        if raw:
            try:
                pathlib.Path(raw).read_bytes()[:1]
                return _answer(card, "run_log", True, "run log readable")
            except OSError:
                continue
    return _answer(card, "run_log", False, "no run log reachable")


def _shared_dir() -> pathlib.Path:
    """A directory that outlives one card under the same account: the parent of the per-card temporary directory."""
    return pathlib.Path(tempfile.gettempdir()).resolve().parent / "gl-cross-card-state"


def cross_card_state(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """FDA-18 residual: can one card leave state that a LATER card of the campaign reads? Each card writes a marker into
    a directory outside its own per-card temp directory and counts the markers it finds there. REACHED on any card
    that finds a marker left by an earlier one."""
    try:
        shared = _shared_dir()
        shared.mkdir(exist_ok=True)
        seen = sum(1 for x in shared.iterdir() if x.name.startswith("card-"))
        (shared / f"card-{uuid.uuid4().hex}").write_bytes(b"")
        return _answer(card, "cross_card_state", seen > 0, f"{seen} earlier marker(s) found")
    except OSError as exc:
        return _answer(card, "cross_card_state", False, type(exc).__name__)


def channel_verdicts(rationales: list[str]) -> dict[str, str]:
    """REACHED if any card of a channel reached it; REFUSED only if every card was refused."""
    out: dict[str, str] = {}
    for text in rationales:
        channel, verdict, _ = (text.split(":", 2) + ["", ""])[:3]
        if channel in CHANNELS:
            out[channel] = REACHED if REACHED in (verdict, out.get(channel)) else REFUSED
    return out


def verify_deployment(run: Any, scan_findings: list[Any] | None = None) -> dict[str, Any]:
    """Run every attack once through ``run(attack_spec) -> rationales``, which the operator binds to the v0.3 harness in
    the OD-20 deployment, and take the proposer-side secret-inventory scan (:mod:`.secret_scan`, FDA-19). Verified only
    if every channel is REFUSED and the scan ran and found nothing."""
    verdicts = {}
    for channel in CHANNELS:
        verdicts.update(channel_verdicts(run(f"benchmarks.genesis_lite.v0_3.deployment_attacks:{channel}")))
    missing = sorted(set(CHANNELS) - set(verdicts))
    return {"verdicts": verdicts, "missing": missing, "secret_scan": scan_findings,
            "verified": not missing and all(v == REFUSED for v in verdicts.values()) and scan_findings == []}
