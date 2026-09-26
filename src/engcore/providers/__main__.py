"""``python -m engcore.providers``: operational provider discovery (installed / unavailable / version / capability).

Introspection only: providers are listed in id order, never ranked, never selected.
"""

from __future__ import annotations

import json
import sys

from .catalog import default_registry


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    statuses = default_registry().discover()
    if "--json" in args:
        print(json.dumps([s.to_dict() for s in statuses], indent=1, sort_keys=True))
        return 0
    for s in statuses:
        c = s.capability
        line = f"{c.provider_id:<14} {s.availability.value:<12} {s.version or '-':<16} {c.family:<16} {c.mode.value:<8}"
        print(line + (f" {s.reason}" if not s.available else f" {c.license}"))
    print("# descriptive capability, not applicability; no provider is ranked or auto-selected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
