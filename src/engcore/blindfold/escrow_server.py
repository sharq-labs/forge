"""Escrow child process: JSON lines in -> JSON lines out.

Run by :class:`~.escrow.SubprocessTransport` (stdin/stdout) or by :mod:`.isolation` (``--fd``: one end of a socket pair
inherited from the launcher).  With ``--storage DIR`` the escrow's secret, identity and journal live in that private
directory and every restart resumes the journaled state; without it the secrets are generated here and die with the
process.  This module never prints a secret except the operator credential, once, in the handshake to the launcher.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys

from .escrow import PROTOCOL, SECURITY_LABEL, EscrowService, EscrowStorage


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--storage", default="")
    ap.add_argument("--fd", type=int, default=-1)
    ap.add_argument("--boundary", default=SECURITY_LABEL, choices=[SECURITY_LABEL],
                    help="what the escrow states about itself: always NOT PROVEN (a verified level is the demo's record)")
    args = ap.parse_args(argv)
    storage = EscrowStorage(args.storage, create=True) if args.storage else None
    service = EscrowService(transport_label="isolated" if args.fd >= 0 else "subprocess", storage=storage,
                            security_boundary=args.boundary)
    hello = json.dumps({"protocol": PROTOCOL, "operator_token": service.operator_token, "escrow_public": service.identity_public})
    # the handshake goes to the launcher on stdout; requests come over stdin or the inherited socket
    sys.stdout.buffer.write(hello.encode() + b"\n")
    sys.stdout.buffer.flush()
    if args.fd >= 0:
        sock = socket.socket(fileno=args.fd)
        reader, writer = sock.makefile("rb"), sock.makefile("wb")
    else:
        reader, writer = sys.stdin.buffer, sys.stdout.buffer
    for line in reader:
        if not line.strip():
            continue
        writer.write(service.handle(line.strip()) + b"\n")
        writer.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
