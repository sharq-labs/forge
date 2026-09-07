"""A digest taken over CRLF bytes is a pin that only holds on one machine.

Every frozen experiment in this repository pins its inputs by SHA-256 over
``path.read_bytes()``. `.gitattributes` sets ``* text=auto eol=lf`` so that a
checkout always materialises LF and those digests mean the same thing
everywhere -- its own comment says the alternative was measured: with
``core.autocrlf=true`` and no attributes file, a clean clone reproduced six
mismatched pins on a tree with no edits in it.

That guarantee has one hole, and it is not in Git. **An editing tool can write
CRLF back into the working tree**, and Git will not object: it normalises on
hash, so ``git status`` stays clean and ``git hash-object`` agrees with the
blob. Only a digest taken over the raw bytes disagrees -- and it disagrees
*somewhere else*, on the next clean checkout, long after whoever caused it has
moved on.

It happened. The thermal re-freeze recomputed four domain digests and two
config digests through Python's text mode on Windows, which writes CRLF. Every
pin test passed locally and all six failed in a clean checkout of the same
commit. The re-pin was correct; the bytes it was taken over were not.

So this file checks the one property that makes a pin portable: **no pinned
file contains a carriage return.**

DO NOT REPLACE THIS WITH A DIGEST CHECK
---------------------------------------
That is the obvious refactor and it removes the entire value. Digest checks
already exist, one per frozen experiment, and they are precisely what did not
help: **they were green on the machine that produced the fault.** A digest can
only compare the bytes in front of it against a number taken from the bytes in
front of it, so when the same wrong bytes produce both, it agrees with itself.
Its failure surfaces on the *next clean checkout*, which is someone else's
machine, after the person who could explain it has moved on.

This check is different in exactly one way, and the way is the point: it tests
a property of the bytes that does not depend on any recorded number. A
carriage return in a pinned file is wrong whether or not a digest was taken
over it, whether or not the digest matches, and whether or not anyone has
re-pinned yet. So it fails **in the run that causes the fault**, on the machine
that caused it, while the cause is still on screen — the only place the
information is cheap.

Concretely: the thermal re-freeze re-pinned six digests from CRLF bytes. Every
digest test passed. This test would have failed immediately, named the six
files, and cost one minute instead of a bad commit on the default branch.

If a future reader is tempted to fold this into the experiment digest tests
because "it is the same thing" — it is not, and the difference is which machine
finds out.
"""

from __future__ import annotations

import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CR = b"\r"


def _pinned_paths() -> dict[str, str]:
    """Every path any frozen experiment pins, mapped to the map that pins it.

    Read off the config modules rather than listed here, so an experiment that
    adds a pin is covered the day it lands. That is the same reason
    `.gitattributes` refuses to scope itself to the pinned paths.
    """
    from experiments.electrical_e2.e2_config import E1_FROZEN_FILE_DIGESTS
    from experiments.electrical_e3.e3_config import E2_FROZEN_FILE_DIGESTS
    from experiments.thermal_t1.t1_config import THERMAL_FROZEN_FILE_DIGESTS
    from experiments.thermal_t2.t2_config import T1_FROZEN_FILE_DIGESTS
    from experiments.thermal_t3.t3_config import T2_FROZEN_FILE_DIGESTS

    maps = {
        "thermal_t1.THERMAL_FROZEN_FILE_DIGESTS": THERMAL_FROZEN_FILE_DIGESTS,
        "thermal_t2.T1_FROZEN_FILE_DIGESTS": T1_FROZEN_FILE_DIGESTS,
        "thermal_t3.T2_FROZEN_FILE_DIGESTS": T2_FROZEN_FILE_DIGESTS,
        "electrical_e2.E1_FROZEN_FILE_DIGESTS": E1_FROZEN_FILE_DIGESTS,
        "electrical_e3.E2_FROZEN_FILE_DIGESTS": E2_FROZEN_FILE_DIGESTS,
    }
    return {rel: name for name, m in maps.items() for rel in m}


PINNED = _pinned_paths()


def test_the_sweep_found_the_pins_or_it_proves_nothing():
    """A guard on the guard: an empty inventory passes every assertion below."""
    assert len(PINNED) >= 30, sorted(PINNED)
    # the two trees that carry the most, named so a silent narrowing shows up
    assert any("conduction1d" in rel for rel in PINNED)
    assert any(rel.startswith("tests/test_sria_") for rel in PINNED)


@pytest.mark.parametrize("relative", sorted(PINNED))
def test_no_pinned_file_carries_a_carriage_return(relative):
    """The bytes a digest is taken over must be the bytes a checkout produces.

    A failure here does **not** mean the file's content is wrong. It means an
    editor or a script wrote it back in the platform's line ending, so any
    digest recomputed from it will hold on this machine and nowhere else.
    Re-materialise the file as LF and re-pin.
    """
    path = REPO_ROOT / relative
    assert path.is_file(), f"{relative} is pinned by {PINNED[relative]} and absent"
    data = path.read_bytes()
    assert CR not in data, (
        f"{relative} contains a carriage return. It is pinned by "
        f"{PINNED[relative]}, and a SHA-256 over these bytes will not match a "
        f"clean checkout, where `.gitattributes` materialises LF. Convert the "
        f"file to LF and recompute the digest over that."
    )
