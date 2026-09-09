"""One process, one unit registry -- including when threads race for the first.

WHY THIS MODULE EXISTS
----------------------
``registry()`` is the Scientific Core's single source of unit meaning, and two
load-bearing claims are written down about it:

* ``_canonical_unit``'s docstring says it is safe to memoize a pint object
  because the registry "is built exactly once ... and **no path in this
  repository ever replaces it**";
* ``tests/test_unit_memoization``'s own docstring repeats it -- "built once
  behind an ``is None`` guard with no path anywhere that replaces it".

Both were true of single-threaded execution and false of concurrent first use.
``if _REGISTRY is None`` is a test and an assignment with a ~0.16 s registry
build between them, so every thread that arrives during that window fails the
test, builds its own registry, and assigns over whatever landed first. Eight
threads produced eight registries and handed seven callers an object the module
no longer holds.

WHAT THAT DID AND DID NOT COST
------------------------------
It did **not** move a scientific answer, and the tests below say so rather than
leaving it to be assumed: pint's dimensionality containers compare and hash by
content, so two registries agree on every compatibility decision, and
:class:`Quantity` stores a unit *string* and re-reads it, so no engcore value
carries a registry identity that could go stale. What it cost was one registry
build per racing thread, and the truth of the sentence the memo's safety
argument rests on. A cache whose justification is "the thing it depends on
never changes" needs that to be a guarantee rather than a habit.

So these tests pin the guarantee itself, not a symptom of it.
"""

from __future__ import annotations

import threading

import pytest

from src.engcore.scientific.units import quantity as unit_module
from src.engcore.scientific.units.quantity import Quantity, dimension_of


THREADS = 8


@pytest.fixture
def cold_registry():
    """Run the body against an uninitialised registry, and put it back after.

    The module globals are restored to the objects the rest of the session is
    already using, and the memo is dropped, so a test that deliberately builds
    a second registry cannot leave this process reading units through it.
    """
    saved = (
        unit_module._REGISTRY,
        unit_module._SEALED_SNAPSHOT,
        unit_module._SEALED_DIGEST,
    )
    unit_module._REGISTRY = None
    unit_module._SEALED_SNAPSHOT = None
    unit_module._SEALED_DIGEST = None
    unit_module.clear_unit_caches()
    try:
        yield
    finally:
        (
            unit_module._REGISTRY,
            unit_module._SEALED_SNAPSHOT,
            unit_module._SEALED_DIGEST,
        ) = saved
        unit_module.clear_unit_caches()


def _race_for_the_registry(monkeypatch):
    """Start ``THREADS`` threads on a barrier and let them all call it first.

    Returns ``(constructed, handed_out)`` -- how many registries were built and
    which objects the callers actually received.
    """
    constructed: list[int] = []
    guard = threading.Lock()
    real_init = unit_module._SealedUnitRegistry.__init__

    def counting_init(self, *args, **kwargs):
        with guard:
            constructed.append(id(self))
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(
        unit_module._SealedUnitRegistry, "__init__", counting_init
    )

    barrier = threading.Barrier(THREADS)
    handed_out: list[int] = []
    seen_guard = threading.Lock()
    failures: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait()
            got = unit_module.registry()
            with seen_guard:
                handed_out.append(id(got))
        except BaseException as exc:  # noqa: BLE001 - reported, not handled
            failures.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not failures, f"a racing caller raised: {failures[0]!r}"
    return constructed, handed_out


def test_threads_racing_for_the_first_registry_build_exactly_one(
    cold_registry, monkeypatch
):
    """The whole point: the guard is a guarantee, not a likely outcome."""
    constructed, _ = _race_for_the_registry(monkeypatch)
    assert len(constructed) == 1, (
        f"{THREADS} threads built {len(constructed)} registries; the memo's "
        f"safety argument requires exactly one for the life of the process"
    )


def test_every_racing_caller_is_handed_the_registry_the_module_kept(
    cold_registry, monkeypatch
):
    """A caller must never hold a registry the module has already replaced."""
    _, handed_out = _race_for_the_registry(monkeypatch)
    assert len(set(handed_out)) == 1, (
        f"callers received {len(set(handed_out))} distinct registries"
    )
    assert handed_out[0] == id(unit_module._REGISTRY)


def test_the_published_digest_describes_the_published_snapshot(
    cold_registry, monkeypatch
):
    """The three globals are one fact, so they must be published together.

    They used to be assigned in two statements, which let one thread's snapshot
    stand beside another thread's digest. Identical builds made the pair agree
    anyway; that is a coincidence and not the invariant.
    """
    _race_for_the_registry(monkeypatch)
    assert unit_module._REGISTRY is not None
    assert unit_module._SEALED_SNAPSHOT is not None
    assert unit_module._SEALED_DIGEST == unit_module._digest_of(
        unit_module._SEALED_SNAPSHOT
    )
    unit_module.verify_registry_unmutated()


def test_the_warm_path_builds_nothing(cold_registry, monkeypatch):
    """Initialisation is once; every later call is a read."""
    constructed, _ = _race_for_the_registry(monkeypatch)
    first = unit_module.registry()
    for _ in range(1000):
        assert unit_module.registry() is first
    assert len(constructed) == 1


def test_units_still_mean_what_they_meant(cold_registry):
    """The synchronisation may not change a single scientific answer."""
    assert Quantity(1000.0, "millivolt").magnitude_in("volt") == pytest.approx(
        1.0
    )
    assert dimension_of("volt") == dimension_of("ampere * ohm")
    assert Quantity(1.0, "volt").units == "volt"
    unit_module.verify_registry_unmutated()
