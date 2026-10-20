"""A stateful proposer for the FDA-18 tests: it remembers, in process memory, how many cards it has seen.

Importable by name (``tests.genesis_lite.stateful_arms:remembers``) so that it runs inside the isolated proposer
process. It answers ``no_law`` on the first card it sees in its process and ``insufficient_evidence`` afterwards, so
the recorded answers show whether one process saw several cards of a campaign.
"""

from __future__ import annotations

from typing import Any, Mapping

_SEEN = {"cards": 0}


def remembers(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    _SEEN["cards"] += 1
    answer = "no_law" if _SEEN["cards"] == 1 else "insufficient_evidence"
    return {"universe_id": card["universe_id"], "answer": answer, "rationale": f"card {_SEEN['cards']} in this process"}


def temp_carry(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    """Leaves a marker in the process's temporary directory and reports whether an earlier card left one there."""
    import tempfile  # noqa: PLC0415
    import pathlib  # noqa: PLC0415

    marker = pathlib.Path(tempfile.gettempdir()) / "gl-temp-carry-marker"
    found = marker.exists()
    marker.write_bytes(b"")
    return {"universe_id": card["universe_id"], "answer": "no_law",
            "rationale": f"temp_carry:{'REACHED' if found else 'REFUSED'}:{tempfile.gettempdir()}"}
