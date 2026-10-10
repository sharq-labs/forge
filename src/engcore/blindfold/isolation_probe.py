"""The HOSTILE proposer of the isolation demo (runs INSIDE the Discovery security domain).

It is handed what a proposer legitimately has -- its campaign id, its OBSERVE capability, the public universe cards,
the escrow's public key, and (as an attacker's guess) the PATHS where the escrow keeps its truth -- and a socket to the
escrow.  It then tries to learn hidden truth every way it can and reports what happened, plus the sha256 of every file
it could read, so the launcher can check that no escrow secret or journal is among them (the secrets themselves are
never sent here).  Nothing in this module can succeed only by being in the escrow's domain: it is the attacker.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
from typing import Any

SCAN_ROOTS = ("/tmp", "/var/tmp", "/dev/shm", "/run", "/home", "/root", "/srv", "/opt", "/mnt")
SKIP_DIRS = ("/mnt/fpy",)                                      # the bind-mounted interpreter (public code)
MAX_FILE = 256 * 1024


class SocketTransport:
    def __init__(self, fd: int) -> None:
        self._sock = socket.socket(fileno=fd)
        self._r, self._w = self._sock.makefile("rb"), self._sock.makefile("wb")

    def __call__(self, request: bytes) -> bytes:
        self._w.write(request.replace(b"\n", b" ") + b"\n")
        self._w.flush()
        line = self._r.readline()
        if not line:
            raise ConnectionError("escrow gone")
        return line


def _try(fn) -> dict[str, Any]:
    try:
        out = fn()
        return {"succeeded": True, "detail": str(out)[:200]}
    except Exception as exc:                                    # noqa: BLE001 - every failure is the expected outcome
        return {"succeeded": False, "detail": f"{type(exc).__name__}: {str(exc)[:160]}"}


def readable_file_digests() -> tuple[list[str], int]:
    digests, scanned = set(), 0
    for root in SCAN_ROOTS:
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            if dirpath.startswith(SKIP_DIRS):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if not d.startswith(".git")]
            for name in filenames:
                path = os.path.join(dirpath, name)
                try:
                    if not os.path.isfile(path) or os.path.getsize(path) > MAX_FILE:
                        continue
                    with open(path, "rb") as fh:
                        digests.add(hashlib.sha256(fh.read()).hexdigest())
                    scanned += 1
                except OSError:
                    continue
    return sorted(digests), scanned


def main() -> int:
    task = json.loads(sys.stdin.read())
    from engcore.blindfold.escrow import (
        PROTOCOL,
        EscrowRefused,
        ObserveClient,
        call,
        mac_request,
        verify_response,
    )
    transport = SocketTransport(int(task["fd"]))
    cid, token, public = task["campaign_id"], task["observe_token"], task["escrow_public"]
    card = task["cards"][0]
    point = {x["name"]: x["range"][0] for x in card["inputs"]}
    report: dict[str, Any] = {"uid": os.getuid(), "euid": os.geteuid(), "pid": os.getpid(),
                              "visible_pids": sorted(int(p) for p in os.listdir("/proc") if p.isdigit()),
                              "network_interfaces": [n for _i, n in socket.if_nameindex()], "attacks": {}}
    a = report["attacks"]
    # --- filesystem and process attacks on the escrow's truth
    for i, path in enumerate(task["truth_paths"]):
        a[f"read_truth_path_{i}"] = _try(lambda p=path: open(p, "rb").read(64))
        a[f"list_truth_dir_{i}"] = _try(lambda p=path: os.listdir(os.path.dirname(p)))
        a[f"traverse_truth_path_{i}"] = _try(lambda p=path: open(os.path.join(os.getcwd(), *[".."] * 12, p.lstrip("/")), "rb").read(64))
    a["environment_has_secrets"] = {"succeeded": any(k.lower() in ("escrow_secret", "operator_token", "master_seed") or "token" in k.lower()
                                                     for k in os.environ), "detail": sorted(os.environ)}
    others = [p for p in report["visible_pids"] if p != os.getpid()]
    a["read_other_process_environ"] = _try(lambda: [open(f"/proc/{p}/environ", "rb").read(64) for p in others] or (_ for _ in ()).throw(
        LookupError("no other process is visible in this pid namespace")))
    a["read_other_process_memory"] = _try(lambda: [open(f"/proc/{p}/mem", "rb").read(1) for p in others] or (_ for _ in ()).throw(
        LookupError("no other process is visible in this pid namespace")))
    a["network_connect_out"] = _try(lambda: socket.create_connection(("1.1.1.1", 443), timeout=2))
    # --- protocol attacks over the only channel it has
    client = ObserveClient(transport, cid, token, escrow_public=public)
    try:
        first = client.observe(card["universe_id"], point, query_id=f"probe-{task['run']}-0")
        report["first_observation_budget_remaining"] = first["budget_remaining"]
        report["observation_keys"] = sorted(first["observation"])
        report["response_leaks_hidden_fields"] = any(k in json.dumps(first) for k in ("\"law\"", "evaluation_points", "\"kind\"", "seed"))
    except EscrowRefused as exc:                                 # a restarted Discovery finds its budget already spent
        report["first_observation_refused"] = str(exc)[:160]
    a["campaign_id_substitution"] = _try(lambda: call(transport, "observe", token=token, campaign_id=task["other_campaign_id"],
                                                      universe_id=card["universe_id"], settings=point, escrow_public=public))
    a["universe_id_substitution"] = _try(lambda: call(transport, "observe", token=token, campaign_id=cid,
                                                      universe_id=task["other_universe_id"], settings=point, escrow_public=public))
    a["score_with_observe_capability"] = _try(lambda: call(transport, "score", token=token, campaign_id=cid, universe_id=card["universe_id"],
                                                           proposal={"answer": "no_law"}, proposal_digest="0" * 64, escrow_public=public))
    a["operator_with_observe_capability"] = _try(lambda: call(transport, "log", operator_token=token, campaign_id=cid, escrow_public=public))
    raw = mac_request({"protocol": PROTOCOL, "op": "observe", "query_id": f"replay-{task['run']}", "last_sequence": -1, "campaign_id": cid,
                       "universe_id": card["universe_id"], "settings": point}, token)
    transport(json.dumps(raw).encode())
    a["credential_replay"] = {"succeeded": json.loads(transport(json.dumps(raw).encode())).get("ok") is True, "detail": "same bytes twice"}
    old = json.loads(transport(json.dumps(mac_request({**{k: v for k, v in raw.items() if k != "mac"},
                                                       "query_id": f"old-{task['run']}"}, token)).encode()))
    fresh = mac_request({**{k: v for k, v in raw.items() if k != "mac"}, "query_id": f"fresh-{task['run']}"}, token)
    a["accept_replayed_old_response"] = _try(lambda: verify_response(old, escrow_public=public, request=fresh))
    junk_ok = []
    for junk in (b"\xff", b"[]", b"{}", json.dumps({"protocol": PROTOCOL, "op": "observe"}).encode(), b"A" * 5000):
        junk_ok.append(json.loads(transport(junk)).get("ok"))
    a["malformed_requests_accepted"] = {"succeeded": any(junk_ok), "detail": str(junk_ok)}
    spent = 0
    try:
        for i in range(1000):
            client.observe(card["universe_id"], point, query_id=f"over-{task['run']}-{i}")
            spent += 1
        a["over_query_beyond_budget"] = {"succeeded": True, "detail": "budget never ran out"}
    except EscrowRefused as exc:
        a["over_query_beyond_budget"] = {"succeeded": False, "detail": f"refused after {spent} more queries: {str(exc)[:80]}"}
    report["readable_file_digests"], report["files_scanned"] = readable_file_digests()
    sys.stdout.write(json.dumps(report, sort_keys=True))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
