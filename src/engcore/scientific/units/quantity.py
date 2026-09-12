"""Scientific quantity contract.

Design position: we do not reimplement dimensional analysis. Pint owns the
unit algebra; this module owns the *contract* — an immutable, serializable
quantity type that the rest of the Scientific Core depends on, so that the
units backend stays replaceable and never leaks into scientific records.

Invariants:

* a Quantity always carries a unit (``"dimensionless"`` is a unit, not an
  absence of one);
* unit strings are normalized on construction, so serialization is
  deterministic;
* incompatible operations raise :class:`UnitCompatibilityError` — the core
  never silently strips or coerces units;
* **a magnitude is always finite.** NaN and ±Inf are refused here, which is
  what keeps them out of parameters, bounds, tolerances, results,
  uncertainties and provenance without a check in each of those types.

  The one sanctioned home for non-finite numbers is
  :class:`~engcore.scientific.solvers.protocol.RawSolverOutput`: a diverged
  backend must be able to report NaN honestly. The boundary is therefore
  *raw backend output may be non-finite; interpreted science may not*.
"""

from __future__ import annotations

import hashlib
import math
import operator as _operator
import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

import pint

from ..errors import UnitCompatibilityError, UnitRegistryMutationError
from ..serialization import require_schema, schema_string

QUANTITY_SCHEMA = schema_string("quantity")

#: Every route pint offers for changing a registry after it exists, named so
#: the sealed registry can refuse each one by the name a caller would reach
#: for. The list is not the guarantee -- :meth:`_SealedUnitRegistry.__setattr__`
#: below refuses *any* attribute assignment, which is what covers the flags
#: (``autoconvert_offset_to_baseunit``, ``default_format``, ``default_system``,
#: ``formatter``, ``force_ndarray`` ...) without anyone having to remember
#: them. These are the callables, which an attribute guard cannot see.
_SEALED_MUTATORS: tuple[str, ...] = (
    # definition surface
    "define",
    "load_definitions",
    "_define",
    "_add_unit",
    "_add_prefix",
    "_add_dimension",
    "_add_derived_dimension",
    "_add_alias",
    "_add_defaults",
    "_add_group",
    "_add_system",
    "_redefine",
    "_register_adder",
    # context surface: enabling a context changes what conversions mean
    "add_context",
    "remove_context",
    "enable_contexts",
    "disable_contexts",
    "context",
    "with_context",
    # display surface, which reaches serialization
    "setup_matplotlib",
)

#: Registry attributes that are behaviour rather than definitions. They cannot
#: be assigned once sealed, so they are here for the *fingerprint* rather than
#: for enforcement -- see :func:`registry_fingerprint`.
_SEALED_FLAGS: tuple[str, ...] = (
    "autoconvert_offset_to_baseunit",
    "autoconvert_to_preferred",
    "force_ndarray",
    "force_ndarray_like",
    "case_sensitive",
    "non_int_type",
    "default_system",
)


def _refusal(operation: str):
    """A sealed stand-in for one of pint's mutators.

    Not a blanket refusal: the same methods build the registry in the first
    place, so each defers to pint until the seal is set and refuses afterwards.
    """

    def refuse(self, *args: Any, **kwargs: Any):
        if self.__dict__.get("_crafty_sealed", False):
            raise UnitRegistryMutationError(
                f"the Scientific Core unit registry is sealed: "
                f"{operation}() would change the units backend for every run "
                f"in this process, and for the meaning of every unit string "
                f"already serialized. A unit this repository does not define "
                f"is not a run's to add; add it to the sealed baseline in "
                f"engcore.scientific.units instead."
            )
        return getattr(pint.UnitRegistry, operation)(self, *args, **kwargs)

    refuse.__name__ = operation
    refuse.__qualname__ = f"_SealedUnitRegistry.{operation}"
    return refuse


class _SealedUnitRegistry(pint.UnitRegistry):
    """A pint registry that refuses to change once it has been built.

    See :class:`~engcore.scientific.errors.UnitRegistryMutationError` for why
    the choice here is refusal rather than a registry per run.

    The refusal is on the registry itself rather than on a proxy around it,
    and that is the difference between a guard and a suggestion: a pint
    ``Quantity`` carries a reference back to the registry that made it, so
    ``registry().Quantity(1, "V")._REGISTRY`` hands any caller the real object.
    A proxy would have been one attribute access from irrelevant. This *is*
    the real object.
    """

    def _seal(self) -> None:
        self.__dict__["_crafty_sealed"] = True

    def __setattr__(self, name: str, value: Any) -> None:
        if self.__dict__.get("_crafty_sealed", False):
            raise UnitRegistryMutationError(
                f"the Scientific Core unit registry is sealed: setting "
                f"{name!r} would change how every run in this process reads "
                f"and renders units"
            )
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if self.__dict__.get("_crafty_sealed", False):
            raise UnitRegistryMutationError(
                f"the Scientific Core unit registry is sealed: deleting "
                f"{name!r} would change how every run in this process reads "
                f"and renders units"
            )
        super().__delattr__(name)


for _operation in _SEALED_MUTATORS:
    if hasattr(pint.UnitRegistry, _operation):
        setattr(_SealedUnitRegistry, _operation, _refusal(_operation))
del _operation


_REGISTRY: _SealedUnitRegistry | None = None
_SEALED_SNAPSHOT: dict[str, dict[str, str]] | None = None
_SEALED_DIGEST: str | None = None

#: Held only while the registry is being built. The warm path never acquires
#: it -- see :func:`registry` for why that is safe and what it costs.
_REGISTRY_LOCK = threading.Lock()


def registry() -> pint.UnitRegistry:
    """The single unit registry owned by the Scientific Core.

    Deliberately *not* pint's application registry: that is process-global and
    mutable by any co-resident library, which would make our dimensional
    guarantees depend on unrelated code.

    It is also deliberately **not** one registry per run. That was the other
    candidate and it is the wrong one, for a reason that is about this
    repository's own value type rather than about cost. :class:`Quantity` is a
    magnitude and a unit *string*; it serializes as a string, is compared
    across runs as a string, and is read back by a reader who was not present
    for the run that wrote it. Per-run registries would let ``"volt"`` mean one
    thing in the run that wrote a record and another in the run that reads it,
    with nothing in the record able to say which -- trading a mutation hazard
    for an interpretation hazard, and a louder one for a silent one.

    The cost that buys, measured rather than asserted: a fresh
    ``pint.UnitRegistry()`` takes ~0.16 s to build on the machine this was
    written on, against ~0.1 ms for a ``Quantity`` construction. Per-run
    isolation would have added ~0.16 s to each of the 1400 hard-benchmark
    cases -- roughly 224 s onto an 80 s scoring run -- and there is no run
    context threaded through this function to hang a registry on, so every
    caller outside a run would have quietly fallen back to a shared one
    anyway. The refusal costs nothing on any path.

    What the refusal covers, exactly: every callable in
    :data:`_SEALED_MUTATORS`, and *any* attribute assignment or deletion on
    the registry. What it does not cover is a caller reaching past pint's API
    into the definition containers themselves (``registry()._units.maps[0]``).
    That half is **detected, not prevented** -- see
    :func:`verify_registry_unmutated`.

    The snapshot is taken *before* the seal is set, because taking it is a
    read through the same object the seal is about to close.

    **Built once means built once, including under threads.** A bare
    ``if _REGISTRY is None`` is a test and an assignment with a ~0.16 s build
    between them, so every thread arriving inside that window failed the test
    and built its own -- eight threads produced eight registries and left seven
    callers holding an object this module no longer had. That did not move a
    scientific answer (pint's dimensionality containers compare and hash by
    content, and :class:`Quantity` stores a unit *string* it re-reads, so no
    engcore value carries a registry identity that can go stale) but it did
    falsify the sentence :func:`_canonical_unit`'s safety argument rests on:
    that nothing ever replaces this object. A memo justified by "the thing it
    depends on never changes" needs that to be a guarantee.

    So construction is behind :data:`_REGISTRY_LOCK`, tested again inside it,
    and the three globals are published in **one** statement -- they are one
    fact, and assigning them in two let one thread's snapshot stand beside
    another thread's digest.

    The warm path is unchanged and deliberately takes no lock: it is the same
    global read and ``is None`` test it always was, because a module global is
    rebound atomically and the value is only ever published fully built and
    already sealed. The lock is on the cold path alone, which runs once.
    """
    global _REGISTRY, _SEALED_SNAPSHOT, _SEALED_DIGEST
    if _REGISTRY is None:
        with _REGISTRY_LOCK:
            # Re-read under the lock: the thread that held it may have been
            # the one that built this.
            if _REGISTRY is None:
                built = _SealedUnitRegistry()
                snapshot = _snapshot_of(built)
                built._seal()
                _REGISTRY, _SEALED_SNAPSHOT, _SEALED_DIGEST = (
                    built,
                    snapshot,
                    _digest_of(snapshot),
                )
    return _REGISTRY


_SNAPSHOT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("unit", "_units"),
    ("prefix", "_prefixes"),
    ("dimension", "_dimensions"),
    ("context", "_contexts"),
    ("system", "_systems"),
    ("group", "_groups"),
)


def _declaration_text(definition: Any) -> str:
    """One declaration, rendered by what it *says* rather than by where it is.

    Units, prefixes and dimensions are pint definition records with a
    content-bearing ``__repr__``, and those go in verbatim. Contexts, systems
    and groups are plain objects that never got one, so ``repr`` on them
    returns ``<pint.System object at 0x...>`` -- **an address**. All 35 of them
    in a default registry are of that kind, which made the digest over this
    snapshot a different value in every process.

    Two things were wrong with that, and only one of them was theoretical:

    * :func:`registry_fingerprint` is documented as "the value a record can
      cite to say *which* unit definitions its numbers were computed against".
      An address hash cannot be that. Two runs over identical definitions
      disagreed, and a run over *changed* ones was indistinguishable from one
      that was not. Nothing in this repository cites it yet -- which is the
      only reason no record is wrong -- but the docstring recommends exactly
      the use the value cannot support.
    * :func:`verify_registry_unmutated` compares this snapshot against itself
      later in the same process, where the addresses are stable because the
      objects are. So it passed, and it would have gone on passing through any
      in-place edit to a context, system or group: it was watching object
      identity, not content, for three of its six sections.

    What is compared instead is each object's own declared content. **What is
    still not compared** is the body of a context transformation: pint compiles
    those from the definition text and keeps the callable, not the source, so
    only the transformation's key is here. That is the same class of hole as a
    caller reaching past pint's API into ``_units.maps[0]`` -- named here so it
    is a known limit rather than an assumed absence.
    """
    kind = type(definition).__name__
    if kind == "Context":
        return repr((
            kind,
            definition.name,
            tuple(sorted(definition.aliases)),
            tuple(
                sorted(
                    (str(key), str(value))
                    for key, value in dict(definition.defaults).items()
                )
            ),
            tuple(sorted(str(key) for key in dict(definition.funcs))),
        ))
    if kind == "System":
        return repr((
            kind,
            definition.name,
            tuple(sorted(definition.members)),
            tuple(
                sorted(
                    (str(unit), str(sorted(dict(expansion).items())))
                    for unit, expansion in dict(definition.base_units).items()
                )
            ),
            tuple(sorted(map(str, definition.derived_units))),
        ))
    if kind == "Group":
        return repr((
            kind,
            definition.name,
            tuple(sorted(definition._unit_names)),
            tuple(sorted(definition._used_groups)),
        ))
    return repr(definition)


def _snapshot_of(reg: pint.UnitRegistry) -> dict[str, dict[str, str]]:
    """Every declaration the registry's arithmetic reads, as text.

    Rendered by content, never by address -- see :func:`_declaration_text`.
    """
    snapshot: dict[str, dict[str, str]] = {}
    for label, attribute in _SNAPSHOT_SECTIONS:
        mapping = getattr(reg, attribute, None)
        if mapping is None:  # pragma: no cover - a backend without the facet
            continue
        snapshot[label] = {
            str(name): _declaration_text(mapping[name]) for name in mapping
        }
    snapshot["flag"] = {
        flag: repr(getattr(reg, flag, None)) for flag in _SEALED_FLAGS
    }
    return snapshot


def _digest_of(snapshot: Mapping[str, Mapping[str, str]]) -> str:
    digest = hashlib.sha256()
    for label in sorted(snapshot):
        digest.update(f"\x1d{label}".encode())
        section = snapshot[label]
        for name in sorted(section):
            digest.update(f"{name}\x1f{section[name]}\x1e".encode())
    return digest.hexdigest()


def _is_a_prefix_of_a_sealed_unit(
    reg: pint.UnitRegistry, name: str, sealed_units: Mapping[str, str]
) -> bool:
    """Is ``name`` a unit pint built itself out of sealed parts?

    Pint materialises prefixed units lazily: ``"millivolt"`` is not in the
    registry until something asks for it, and then it is, written into the
    same mapping the declared units live in. So a name appearing after the
    seal is *usually* pint doing its own job and carries no new information --
    but only if it really is ``prefix + sealed unit``, with the prefix's own
    scale, and the same reference as the unit it prefixes. A hand-written
    entry that merely looked like one would not survive those three tests, and
    a shadowing ``"millivolt"`` worth 3 metres is precisely the mutation this
    has to tell apart from the harmless case.
    """
    units, prefixes = reg._units, reg._prefixes
    definition = units.get(name)
    if definition is None:  # pragma: no cover - it was read from this mapping
        return False
    for prefix_name in prefixes:
        text = str(prefix_name)
        if not text or not name.startswith(text):
            continue
        base_name = name[len(text) :]
        if base_name not in sealed_units:
            continue
        base = units[base_name]
        expected_reference = type(base.reference)({base_name: 1})
        if getattr(definition, "reference", None) != expected_reference:
            continue
        prefix_value = getattr(prefixes[prefix_name], "value", None)
        scale = getattr(getattr(definition, "converter", None), "scale", None)
        if prefix_value is None or scale is None:
            continue
        if float(scale) == float(prefix_value):
            return True
    return False


def registry_fingerprint() -> str:
    """The digest of the declarations the registry was sealed with.

    Stable for the life of the process by construction -- it is taken once,
    when the registry is built -- so it is the value a record can cite to say
    *which* unit definitions its numbers were computed against.

    **Reproducible across processes, which it was not.** The snapshot behind it
    used to render three of its six sections with the default ``repr`` of an
    object that has none, so the digest hashed memory addresses and every
    process got a different one. It identified a run, not a set of definitions
    -- the opposite of what the sentence above claims of it. It now renders
    every declaration by content; see :func:`_declaration_text`, which also
    names the one thing still outside it.
    """
    registry()
    return _SEALED_DIGEST or ""


def verify_registry_unmutated() -> None:
    """Refuse if the registry's declarations have moved since it was sealed.

    This is a **detector, not an enforcer**, and the distinction is the point.
    :class:`_SealedUnitRegistry` *prevents* every mutation that goes through
    pint's API or through an attribute, and that prevention needs nobody to
    call anything. It cannot prevent a caller from writing straight into
    ``registry()._units.maps[0]``, because that is a plain dictionary owned by
    the backend. Nothing in this repository does that. If something starts,
    this is what says so -- but it says so when it is called, not when the
    write happens, and calling it is opt-in in a way the refusal is not.
    """
    registry()
    assert _REGISTRY is not None and _SEALED_SNAPSHOT is not None
    current = _snapshot_of(_REGISTRY)
    for label, sealed_section in _SEALED_SNAPSHOT.items():
        now = current.get(label, {})
        for name, sealed_text in sealed_section.items():
            if name not in now:
                raise UnitRegistryMutationError(
                    f"the sealed unit registry lost the {label} {name!r}; "
                    f"every quantity computed since is suspect"
                )
            if now[name] != sealed_text:
                raise UnitRegistryMutationError(
                    f"the sealed unit registry's {label} {name!r} was "
                    f"redefined behind the seal: {sealed_text} became "
                    f"{now[name]}; every quantity computed since is suspect"
                )
        for name in now:
            if name in sealed_section:
                continue
            if label == "unit" and _is_a_prefix_of_a_sealed_unit(
                _REGISTRY, name, sealed_section
            ):
                continue
            raise UnitRegistryMutationError(
                f"the sealed unit registry gained the {label} {name!r}, which "
                f"is not pint's own prefixing of a sealed unit; every quantity "
                f"computed since is suspect"
            )


#: Bound on the memo below. Unit strings come from declarations and payloads and
#: number in the low hundreds for any real process; the bound exists so that a
#: pathological caller cannot grow the table without limit, and a miss merely
#: costs what every call used to cost.
_UNIT_CACHE_SIZE = 4096


@lru_cache(maxsize=_UNIT_CACHE_SIZE)
def _canonical_unit(text: str) -> tuple[str, Any]:
    """``(canonical string, dimensionality)`` for one stripped unit expression.

    WHY THIS IS SAFE TO MEMOIZE, stated rather than assumed
    -------------------------------------------------------
    This is a pure function of ``text`` and the registry, and the registry is a
    constant for the life of the process:

    * it is built exactly once -- under :data:`_REGISTRY_LOCK`, so that holds
      when threads race for the first build too -- and **no path in this
      repository ever replaces it**;
    * it is sealed before it is published -- every mutating callable pint
      offers is refused, as is any attribute assignment or deletion, and
      ``tests/test_core_guards.py`` exercises that enumeration rather than a
      sample of it.

    So the mapping from a unit string to its canonical form and dimensionality
    cannot change while this process runs, and the key is the *entire* varying
    input. Nothing about a model, a threshold, a context or a verdict
    participates in the value, so this is not a scientific-identity cache and
    the completeness question those must answer does not arise here: it caches
    a lexical fact about a unit string.

    **The one residual hole, and it is pre-existing.** A caller reaching past
    pint's API into the definition containers themselves
    (``registry()._units.maps[0]``) can still mutate the registry -- the module
    docstring already says so, and :func:`verify_registry_unmutated` exists to
    detect exactly that. After such a mutation this memo would serve stale
    canonical forms; so would every ``Quantity`` already constructed, and the
    detector still fires. :func:`clear_unit_caches` is provided for the case
    where somebody legitimately needs to reset it.

    **Both halves are returned from one parse.** ``dimension_of`` used to call
    ``normalize_unit`` -- which parsed the string and formatted it back to a
    string -- and then parse that string *a second time* to reach
    ``.dimensionality``, when the first parse had it all along. Two parses and a
    format, for a value the first line already held.
    """
    unit = registry().Unit(text)
    return str(unit), unit.dimensionality


def clear_unit_caches() -> None:
    """Drop the memoized unit tables.

    Not needed in normal operation -- the registry cannot change -- and present
    so that anything which deliberately reaches past the seal has a supported
    way to invalidate what it invalidated.
    """
    _canonical_unit.cache_clear()
    _canonical_dimensionality.cache_clear()
    # Every memo in this module, not only the first two. `_normalized` and
    # `_conversion_rule` sit in FRONT of `_canonical_unit`, so leaving them
    # populated meant a caller who cleared the caches still got an answer
    # without a parse — and `test_a_repeated_unit_string_is_canonicalised_once`
    # measured zero parses where it expected one. A clear that does not clear
    # everything is worse than none, because what it leaves behind is invisible.
    _normalized.cache_clear()
    _conversion_rule.cache_clear()


def unit_cache_stats() -> dict[str, Any]:
    """Hit/miss counts for the memo, for diagnostics and performance guards.

    The headline numbers stay those of ``_canonical_unit`` — the parse, which
    is what "how often did this cost a parse" means and what the existing
    guards measure. The memos in front of it are reported alongside rather
    than folded in, because adding their hits to the parse count would change
    what the number means.
    """
    info = _canonical_unit.cache_info()
    normalized = _normalized.cache_info()
    conversions = _conversion_rule.cache_info()
    return {
        "hits": info.hits,
        "misses": info.misses,
        "currsize": info.currsize,
        "maxsize": info.maxsize,
        "normalized_hits": normalized.hits,
        "normalized_misses": normalized.misses,
        "conversion_rule_hits": conversions.hits,
        "conversion_rule_misses": conversions.misses,
    }


@lru_cache(maxsize=_UNIT_CACHE_SIZE)
def _normalized(text: str) -> str:
    """The body of :func:`normalize_unit`, memoized on the caller's spelling.

    ``_canonical_unit`` was already memoized, so what this adds is the strip,
    the emptiness check and the exception wrapper — which sound free and are
    not: profiled over a thousand small solves this path ran 188,000 times,
    and ``str.strip`` alone accounted for 253,000 calls. Caching the caller's
    exact spelling rather than the stripped form means ``"K"``, ``" K"`` and
    ``"kelvin"`` each get an entry and all three return the same canonical
    string, which is what they did before.

    Exceptions are not cached by ``lru_cache``, so an unparsable unit is
    re-raised on every call exactly as it was.
    """
    stripped = text.strip()
    if not stripped:
        raise UnitCompatibilityError(
            "unit must be a non-empty string; use 'dimensionless' explicitly"
        )
    try:
        return _canonical_unit(stripped)[0]
    except Exception as exc:  # pint raises several distinct types
        raise UnitCompatibilityError(f"unparsable unit {text!r}: {exc}") from exc


def normalize_unit(unit: str) -> str:
    """Canonical string form of a unit expression.

    Raises :class:`UnitCompatibilityError` for unparsable input.
    """
    # `str(unit)` is kept for callers that pass something string-like, and the
    # common case skips it: a `str` is already hashable and already itself.
    return _normalized(unit if type(unit) is str else str(unit))


@lru_cache(maxsize=_UNIT_CACHE_SIZE)
def base_unit(unit: str) -> str:
    """The SI base unit of this unit's dimension, whose zero is physical.

    Where a ratio or a difference has to be taken across two scales, this is
    the one they can both be put on. Memoized for the same reason as
    :func:`_canonical_unit`: the registry never changes.
    """
    _factor, base = registry().get_base_units(
        registry().Unit(normalize_unit(unit)))
    return str(base)


@lru_cache(maxsize=_UNIT_CACHE_SIZE)
def is_ratio_scale(unit: str) -> bool:
    """Does zero of this unit mean zero of the quantity?

    True for kelvin, ohm, second, ``delta_degC``; false for ``degC`` and
    ``degF``, whose zeros are conventions. It is the property that decides
    whether a RATIO of two values means anything: 20 degC is not twice 10 degC,
    and no amount of careful conversion makes it so.

    The repository already applies this rule in two places and states it the
    same way each time — a coupling tolerance and a temperature excursion span
    are both refused on an affine scale, because a *difference* cannot live on
    a scale with a conventional zero. This is that test, generalised past
    temperature and given a name, because a third caller needed it: a ratio has
    the same requirement as a difference and for the same reason.

    Memoized on the same argument as :func:`_canonical_unit` and safe for
    exactly the same reason — the registry is a constant for the life of the
    process.
    """
    text = normalize_unit(unit)
    base = base_unit(text)
    if base == text:
        return True
    return float(registry().Quantity(0.0, text).to(base).magnitude) == 0.0


@lru_cache(maxsize=_UNIT_CACHE_SIZE)
def _conversion_rule(source: str, target: str) -> tuple[float | None, Any, Any]:
    """How to move a magnitude from ``source`` to ``target``, decided once.

    Returns ``(factor, source_units, target_units)``. A ``factor`` means the
    conversion is a multiply; ``None`` means it must go through the backend,
    and the two parsed unit containers are returned so that call does not
    re-parse either string.

    **Why a multiply is allowed for some pairs and not others.** A conversion
    between two ratio-scale units is ``m * k``, and the backend computes it
    that way, so multiplying by ``convert(1.0)`` reproduces it exactly. A
    conversion across an affine scale is ``m * k + c``, and computing it as
    ``m * (one - zero) + zero`` is *algebraically* the same and *numerically*
    is not: the subtraction and the addition each round, and the result differs
    from the backend's in the last place.

    That is not a tolerable difference. This repository's own certificate
    already records exact float boundary equality as a known limit, and a unit
    layer that returned a different final bit than it did last week would move
    scientific values for no reason a reader could see. So the rule is decided
    by measurement, not by algebra:

    * multiplicative pairs — verified bit-identical to the backend across 133
      unit pairs and 5,412 magnitude cases, including denormals, 1e±300 and
      randomised values — take the multiply;
    * affine pairs — where the same check passes only 40.5 % of the time —
      go to the backend, which still skips the quantity construction and both
      string parses.

    ``tests/test_unit_conversion_equivalence.py`` is that measurement, kept as
    a test so the claim is re-checked rather than remembered.

    Memoized on the pair of canonical unit strings, and safe for exactly the
    reason :func:`_canonical_unit` is: the registry is a constant for the life
    of the process, so the rule for a pair cannot change under the cache.
    """
    backend = registry()
    source_units = backend.Unit(source)._units  # noqa: SLF001 - pint's own container
    target_units = backend.Unit(target)._units  # noqa: SLF001
    zero = float(backend.convert(0.0, source_units, target_units))
    if zero == 0.0:
        return (
            float(backend.convert(1.0, source_units, target_units)),
            source_units,
            target_units,
        )
    return (None, source_units, target_units)


def dimension_of(unit: str) -> Any:
    """A unit's physical dimensionality as the backend's own comparable object.

    This — not :func:`dimensionality` — is what compatibility is decided by.
    Pint's ``UnitsContainer`` is a mapping from dimension name to exponent and
    compares (and hashes) by content, so ``ampere * ohm`` and ``volt`` are
    equal to it. Its *rendering* is not canonical: the exponents come out in
    the order the composite was built, so ``I * R`` renders as
    ``... / [current] / [time] ** 3`` and ``volt`` as
    ``... / [time] ** 3 / [current]``. Comparing those strings made Ohm's law
    a units error; comparing these objects does not.
    """
    # Structurally what it always was -- normalize first, so an unparsable or
    # empty unit raises `normalize_unit`'s message and not this function's --
    # with the second parse replaced by a memo lookup.
    try:
        return _canonical_unit(normalize_unit(unit))[1]
    except UnitCompatibilityError:
        raise
    except Exception as exc:
        raise UnitCompatibilityError(
            f"cannot determine dimensionality of {unit!r}: {exc}"
        ) from exc


def dimensionality(unit: str) -> str:
    """Stable string form of a unit's physical dimensionality.

    For messages, display and serialization. The rendering is **canonical**:
    the dimension names are sorted, so two dimensionally identical units
    always produce the same string no matter how each was composed. Equality
    of these strings is therefore a correct compatibility test as well —
    which matters because callers outside this subpackage do compare them.

    Single-dimension and dimensionless units render exactly as the backend
    renders them (``"[temperature]"``, ``"dimensionless"``); only the ordering
    of a multi-dimension rendering is fixed, and only where it was arbitrary.
    """
    # Memoized on the CANONICAL form rather than on the caller's spelling, so
    # `"K"` and `"kelvin"` share one entry. Same safety argument as
    # `_canonical_unit`: a pure function of the string and a registry that
    # cannot change.
    return _canonical_dimensionality(normalize_unit(unit))


@lru_cache(maxsize=_UNIT_CACHE_SIZE)
def _canonical_dimensionality(canonical: str) -> str:
    dimensions = _canonical_unit(canonical)[1]
    # Rebuilt through the container's own type rather than string-joined by
    # hand, so the rendering stays the backend's and only its order is ours.
    return str(type(dimensions)(dict(sorted(dimensions.items()))))


@dataclass(frozen=True)
class Quantity:
    """A scientific value: magnitude plus unit, never one without the other."""

    magnitude: float
    units: str

    def __post_init__(self) -> None:
        magnitude = float(self.magnitude)
        if not math.isfinite(magnitude):
            raise UnitCompatibilityError(
                f"scientific magnitude must be finite, got {magnitude!r}; "
                f"non-finite values belong in RawSolverOutput diagnostics, "
                f"not in an interpreted scientific quantity"
            )
        object.__setattr__(self, "magnitude", magnitude)
        object.__setattr__(self, "units", normalize_unit(self.units))

    # ---- construction -------------------------------------------------
    @classmethod
    def dimensionless(cls, magnitude: float) -> "Quantity":
        return cls(magnitude, "dimensionless")

    @classmethod
    def parse(cls, text: str) -> "Quantity":
        """Parse ``"12 V"`` style input. Bare numbers are rejected: a
        scientific value without a unit is a contract violation, not a
        dimensionless default."""
        raw = str(text).strip()
        try:
            # A bare numeric literal parses as dimensionless in every units
            # backend; accepting it would silently invent a unit.
            float(raw)
        except ValueError:
            pass
        else:
            raise UnitCompatibilityError(
                f"{raw!r} carries no unit; state one explicitly "
                f"(e.g. '{raw} dimensionless')"
            )
        # SPLIT FIRST, and only fall back to the backend's string parser.
        #
        # ``registry().Quantity("20 degC")`` is read by the backend as the
        # MULTIPLICATION ``20 * degC``, and multiplying by an offset unit is
        # ambiguous, so it refuses. The two-argument constructor never
        # multiplies -- ``Quantity(20.0, "degC").magnitude_in("kelvin")`` is
        # 293.15 and always was -- so the whole of this class supported degrees
        # Celsius except the one path a declaration can take.
        #
        # That cost the payload boundary its most common engineering
        # temperature unit, and it did so while reporting the wrong cause: the
        # message said the quantity could not be READ, when the unit is
        # perfectly readable and only the multiplication was ambiguous. It also
        # contradicted the boundary's own stated rule -- "any unit of the right
        # dimension is accepted; the core converts it" -- which is asserted in
        # tests/mcp/test_problem.py and was only ever exercised with a
        # ratio-scale unit.
        #
        # Found by benchmarks/blind/v1: 72 of 444 cases, across two systems and
        # every boundary stratum, refused for declaring a temperature in degC.
        #
        # The fallback is kept and is not decoration: it takes any spelling the
        # split cannot handle -- "5volt" with no separator among them -- so this
        # is strictly additive. It cannot admit an unknown unit, because the
        # two-argument path normalises through the same registry and
        # ``"1 kilohm"`` is still refused. Nor does it weaken the places that
        # deliberately refuse an affine scale: a coupling tolerance and an
        # excursion span are refused by ``_require_ratio_scale`` on the UNIT,
        # after any parse, and those refusals are about a difference that
        # cannot live on a scale with a conventional zero.
        magnitude, separator, unit = raw.partition(" ")
        if separator and unit.strip():
            try:
                return cls(float(magnitude), unit.strip())
            except (ValueError, UnitCompatibilityError):
                pass
        try:
            parsed = registry().Quantity(raw)
        except Exception as exc:
            raise UnitCompatibilityError(
                f"cannot parse quantity {text!r}: {exc}"
            ) from exc
        return cls(float(parsed.magnitude), str(parsed.units))

    # ---- dimensional interface ----------------------------------------
    @property
    def dimensionality(self) -> str:
        return dimensionality(self.units)

    def is_compatible_with(self, other: "Quantity | str") -> bool:
        target = other.units if isinstance(other, Quantity) else other
        # Objects, not their renderings. See :func:`dimension_of`.
        return dimension_of(self.units) == dimension_of(target)

    def require_compatible(self, other: "Quantity | str", *, context: str = "") -> None:
        if not self.is_compatible_with(other):
            target = other.units if isinstance(other, Quantity) else other
            where = f" ({context})" if context else ""
            raise UnitCompatibilityError(
                f"incompatible units{where}: {self.units!r} "
                f"[{self.dimensionality}] vs {target!r} [{dimensionality(target)}]"
            )

    def to(self, unit: str) -> "Quantity":
        """Convert to ``unit``. Raises if dimensionally incompatible."""
        target = normalize_unit(unit)
        # CONVERTING TO THE UNIT ALREADY CARRIED IS NOT A CONVERSION.
        #
        # `self.units` is canonical (`__post_init__` normalises it) and so is
        # `target`, so equal strings mean the same unit and the conversion below
        # is the identity: pint would build a quantity, multiply by one, and
        # hand back the magnitude it was given.
        #
        # This is not a rare case -- it is almost the only case. Counted over
        # one real coupled run: **549 of 552 calls (99.5 %)** ask for the unit
        # the value already has, because callers reach for `magnitude_in(...)`
        # to get a number out of a value rather than to move it between units.
        #
        # The compatibility check is skipped with it, and cannot change an
        # outcome: a unit is dimensionally compatible with itself. `normalize_unit`
        # still runs first, so an unparsable target is still refused here.
        #
        # `self` is returned rather than a copy. `Quantity` is frozen, so an
        # alias is indistinguishable from an equal copy, and it is what
        # `freeze` already does for every immutable value in this core.
        if target == self.units:
            return self
        self.require_compatible(target, context="conversion")
        # THE CONVERSION IS PERFORMED BY THE BACKEND; WHAT IS MEMOIZED IS THE
        # PARSE, NOT THE ARITHMETIC.
        #
        # This used to build a fresh `pint.Quantity` from `(magnitude, unit
        # string)` on every call, which re-parsed the unit string every time:
        # profiled over a thousand small solves it was 58,000 backend quantity
        # constructions and 58,000 string parses, and the backend was the
        # single largest cost in the run at 41 % of profiled time.
        #
        # `_conversion_rule` caches what does not depend on the magnitude. See
        # its docstring for why a multiplicative pair may be a multiply and an
        # affine one may not.
        factor, source_units, target_units = _conversion_rule(self.units, target)
        if factor is not None:
            return Quantity(self.magnitude * factor, target)
        return Quantity(
            float(registry().convert(self.magnitude, source_units, target_units)),
            target,
        )

    def magnitude_in(self, unit: str) -> float:
        """Numeric magnitude expressed in ``unit`` — the single sanctioned way
        to hand a scientific value to a numeric kernel."""
        return self.to(unit).magnitude

    # ---- minimal arithmetic -------------------------------------------
    # Enough for constraint checks and adapters; full quantity algebra stays
    # in the backend and is not part of this contract.
    def _combine(self, other: "Quantity", operator, *, context: str) -> "Quantity":
        """Addition and subtraction, performed by the backend.

        **This used to be converted-magnitude arithmetic** — convert the right
        operand into the left's unit, apply the operator to the two floats, and
        keep the left's unit. That is correct for every ratio-scale unit and
        wrong for every interval one, and the wrongness is not small:
        ``Q(30, 'degC') - Q(20, 'degC')`` returned ``10 degC``, which converts
        to **283.15 K** rather than to a 10 K difference. On an interval scale
        the difference of two absolute values is not an absolute value; it
        lives on a different unit, and the backend has one. The same rule made
        ``Q(30, 'degC') + Q(20, 'degC')`` return ``50 degC`` — not a wrong
        number but a meaningless one, since adding two absolute temperatures
        has no answer to give.

        So the operation is delegated, which is this module's stated design
        position rather than a new one: *"we do not reimplement dimensional
        analysis. Pint owns the unit algebra; this module owns the contract."*
        Offset-unit and delta-unit semantics come back from the backend intact
        — a Celsius difference lands on ``delta_degree_Celsius``, a delta added
        to an absolute stays absolute, and absolute-plus-absolute raises.

        What this module keeps is the contract around it. The dimensional check
        is made **first**, so an incompatible pair still fails with this
        package's own :class:`UnitCompatibilityError` naming the operation,
        rather than with whatever the backend would have said; and the result
        is rebuilt through :class:`Quantity`, so it is normalised and finite
        like every other value here.

        Ratio-scale behaviour is unchanged, because pint's own rule there is
        already the left operand's unit: ``1 m + 100 cm`` is still ``2 m``.
        """
        self.require_compatible(other, context=context)
        try:
            combined = operator(
                registry().Quantity(self.magnitude, self.units),
                registry().Quantity(other.magnitude, other.units),
            )
        except Exception as exc:  # pint raises several distinct types
            raise UnitCompatibilityError(
                f"cannot perform {context} on {self.units!r} and "
                f"{other.units!r}: {exc}"
            ) from exc
        return Quantity(float(combined.magnitude), str(combined.units))

    def __add__(self, other: "Quantity") -> "Quantity":
        return self._combine(other, _operator.add, context="addition")

    def __sub__(self, other: "Quantity") -> "Quantity":
        return self._combine(other, _operator.sub, context="subtraction")

    def __mul__(self, other: "Quantity | float") -> "Quantity":
        if isinstance(other, Quantity):
            product = (
                registry().Quantity(self.magnitude, self.units)
                * registry().Quantity(other.magnitude, other.units)
            )
            return Quantity(float(product.magnitude), str(product.units))
        return Quantity(self.magnitude * float(other), self.units)

    def __truediv__(self, other: "Quantity | float") -> "Quantity":
        if isinstance(other, Quantity):
            ratio = (
                registry().Quantity(self.magnitude, self.units)
                / registry().Quantity(other.magnitude, other.units)
            )
            return Quantity(float(ratio.magnitude), str(ratio.units))
        return Quantity(self.magnitude / float(other), self.units)

    def compare(self, other: "Quantity") -> float:
        """Signed difference in *this* quantity's units (>0 if self larger)."""
        self.require_compatible(other, context="comparison")
        return self.magnitude - other.to(self.units).magnitude

    # ---- serialization -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": QUANTITY_SCHEMA,
            "magnitude": self.magnitude,
            "units": self.units,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Quantity":
        require_schema(payload, QUANTITY_SCHEMA)
        return cls(float(payload["magnitude"]), str(payload["units"]))

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.magnitude} {self.units}"


def coerce_quantity(value: Quantity | float | int | str, unit: str) -> Quantity:
    """Interpret ``value`` in the declared context ``unit``.

    A bare number is accepted only because ``unit`` supplies the missing
    context explicitly; a Quantity is converted and dimension-checked. This is
    the one sanctioned entry point for numeric input, and it never guesses.
    """
    if isinstance(value, Quantity):
        return value.to(unit)
    if isinstance(value, str):
        return Quantity.parse(value).to(unit)
    return Quantity(float(value), unit)
