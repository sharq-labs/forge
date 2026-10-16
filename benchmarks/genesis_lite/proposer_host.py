"""Isolated proposer process for Genesis-lite (OD-20 hardening): the arm runs HERE, never in the operator's process.

The operator starts one fresh interpreter per campaign (``python -I proposer_host.py <path>...``) with an empty working
directory and a scrubbed environment. This process receives, over stdin, only a presented card and the arm to run; it
asks the operator for observations over stdout and answers with a proposal. It never holds the escrow, the master seed,
the presentation key or a hidden world, so heap scans and stack walks inside it find nothing (tested).

It is a PROCESS separation under the same OS account: it does not stop a proposer from reading files the account can
read, or (where the platform allows) another process's memory. The escrow therefore still states
SECURITY_BOUNDARY_NOT_PROVEN; a proven boundary needs the deployment requirements of OD-20.

Protocol (JSON lines):
  operator -> host  {"op": "propose", "arm": "<registry name>|<module>:<function>", "seed": int, "card": {...}}
  host -> operator  {"op": "observe", "universe_id", "settings", "query_id"}
  operator -> host  {"ok": true, "response": {...}} | {"ok": false, "refused": "..."}
  host -> operator  {"op": "proposal", "proposal": {...}} | {"op": "error", "error": "..."}
"""

from __future__ import annotations

import importlib
import json
import sys


def main(argv: list[str]) -> int:
    for path in reversed(argv):
        sys.path.insert(0, path)
    proto_out, proto_in = sys.stdout.buffer, sys.stdin.buffer
    sys.stdout = sys.stderr                                  # an arm's print() must not corrupt the protocol

    def send(obj: object) -> None:
        proto_out.write(json.dumps(obj).encode() + b"\n")
        proto_out.flush()

    def recv() -> dict:
        line = proto_in.readline()
        if not line:
            raise SystemExit(0)
        return json.loads(line)

    import engcore  # noqa: PLC0415 - imported after the path pins, reported so the operator can refuse a stray copy
    from engcore.blindfold.escrow import EscrowRefused  # noqa: PLC0415

    send({"op": "hello", "engcore": engcore.__file__})

    class Client:
        def observe(self, universe_id: str, settings: dict, query_id: str = "") -> dict:
            send({"op": "observe", "universe_id": universe_id, "settings": dict(settings), "query_id": query_id})
            reply = recv()
            if not reply.get("ok"):
                raise EscrowRefused(str(reply.get("refused", "refused")))
            return reply["response"]

    def resolve(spec: str):
        if ":" in spec:
            module, name = spec.split(":", 1)
            return getattr(importlib.import_module(module), name)
        from benchmarks.genesis_lite.arms import ARMS  # noqa: PLC0415
        return ARMS[spec][0]

    while True:
        msg = recv()
        if msg.get("op") != "propose":
            send({"op": "error", "error": f"unknown operation {msg.get('op')!r}"})
            continue
        try:
            proposal = dict(resolve(msg["arm"])(msg["card"], Client(), seed=int(msg["seed"])))
            send({"op": "proposal", "proposal": proposal})
        except SystemExit:
            raise
        except BaseException as exc:  # noqa: BLE001 - every arm failure is reported, never a dead protocol
            send({"op": "error", "error": f"{type(exc).__name__}: {str(exc)[:400]}"})


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
