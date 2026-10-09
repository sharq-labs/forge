"""Escrow child process: JSON lines on stdin -> JSON lines on stdout.  Secrets are generated here (os.urandom).

Run by :class:`~.escrow.SubprocessTransport`.  Same OS account as the parent: SECURITY_BOUNDARY_NOT_PROVEN.
"""

from __future__ import annotations

import sys

from .escrow import EscrowService


def main() -> int:
    service = EscrowService(transport_label="subprocess")
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        sys.stdout.buffer.write(service.handle(line.strip()) + b"\n")
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
