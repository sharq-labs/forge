"""A canonical, deterministic description of the frozen public Core API.

WHY THIS LIVES IN THE PACKAGE AND NOT IN `tests/`
--------------------------------------------------
It has to run against the INSTALLED WHEEL, from a process with no source
checkout on ``sys.path``, to answer Part Q's question: does the wheel expose
the same API the source does. A snapshot tool that only exists in the
repository can compare the repository against itself.

WHAT "CANONICAL" MEANS HERE, and what it deliberately excludes
---------------------------------------------------------------
The snapshot is a fact about the API's SHAPE. Two runs of the same code must
produce the same bytes, on any machine, in any directory, under any hash seed.
So nothing here may read:

* a memory address, or any ``repr`` that embeds one -- the reason defaults are
  rendered by :func:`_render_default` rather than by ``repr``;
* a filesystem path, a checkout location or a working directory;
* a timestamp, a process id or an environment variable;
* dict insertion order or set iteration order -- every collection is sorted
  before it is written;
* ``id()``, ``hash()`` of anything unordered, or anything else that varies with
  ``PYTHONHASHSEED``.

Signatures are read with :mod:`inspect`, which gives parameter KIND
(positional-only, positional-or-keyword, keyword-only, var-positional,
var-keyword) as well as name and default. Kind is part of the contract: moving
an argument from keyword-only to positional-or-keyword is a compatibility event
even though every existing call still works.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import importlib
import inspect
import json
from typing import Any

_INF = float("inf")

#: Canonical import paths. A frozen symbol is frozen AT one of these; the same
#: object reachable through a deeper module path is an implementation detail.
CANONICAL_MODULES = (
    "engcore.scientific",
    "engcore.data",
    "engcore.inference",
    "engcore.uq",
    "engcore.adequacy",
    "engcore.execution",
    "engcore.studies",
)

SCHEMA = "engcore.api_snapshot/1"

#: Core V2 is ADDITIVE: it adds canonical modules and changes none of the seven
#: above. The V1 contract is the snapshot of `CANONICAL_MODULES` alone, and
#: `build()` with no argument keeps producing it byte-for-byte -- the V1 freeze
#: verifier, its reproduction probe and the V1 wheel parity script all call it
#: that way, so a V2 name can never move the V1 frozen digest. The V2 contract
#: is the snapshot of `V2_CANONICAL_MODULES`; see docs/CORE_V2_API_DESIGN.md.
V2_ADDED_MODULES = ("engcore.hybrid_uq",)
V2_CANONICAL_MODULES = CANONICAL_MODULES + V2_ADDED_MODULES

#: Parameters whose stability classification is not FREEZE, keyed by
#: ``"module:symbol:parameter"``. Recorded here rather than inferred, so an
#: experimental surface is a written decision.
EXPERIMENTAL_PARAMETERS = {
    "engcore.execution:run_sweep:workers",
    "engcore.execution:rerun_failed:workers",
}

#: PART S -- the deprecation registry. Currently EMPTY, and that emptiness is
#: the claim: nothing in the frozen Core API is on its way out.
#:
#: An empty registry still needs the mechanism, because the first deprecation
#: is exactly when nobody will want to design one. Each entry is keyed by
#: ``(module, name)`` and MUST carry all five fields:
#:
#: ``reason``        why it is going away, in terms of what it got wrong;
#: ``replacement``   the symbol to use instead, or ``None`` said explicitly --
#:                   "there is no replacement" is a legitimate answer and a
#:                   very different one from having forgotten to write it;
#: ``category``      the warning class the symbol raises when used. Must be
#:                   ``DeprecationWarning`` (or a subclass), never
#:                   ``UserWarning``: Python silences DeprecationWarning by
#:                   default outside ``__main__``, which is the behaviour a
#:                   library WANTS -- an application author sees it when they
#:                   go looking, and an end user is not spammed by a library
#:                   they did not write;
#: ``since``         the freeze-policy version that deprecated it;
#: ``removal``       the version it may be removed in, which under the freeze
#:                   policy is never earlier than the next MAJOR.
#:
#: A DEPRECATED symbol stays in the FROZEN snapshot. Deprecation is a statement
#: about the future; the contract is still in force until it is removed, and a
#: symbol that vanished from the frozen surface the moment it was deprecated
#: would let a removal happen without ever being a compatibility event.
DEPRECATED_SYMBOLS: dict[tuple[str, str], dict[str, Any]] = {}

#: The fields every registry entry must carry. Named here rather than in the
#: test so the rule ships with the package a consumer actually installs.
DEPRECATION_FIELDS = ("reason", "replacement", "category", "since", "removal")

#: Individual symbols that are public but NOT frozen, keyed by
#: ``(module, name)``, with the reason. Module granularity is not enough: a
#: package can be a genuine Core contract and still carry one spike, and the
#: alternative to saying so here is to freeze the spike or to stop exporting it.
EXPERIMENTAL_SYMBOLS = {
    ("engcore.inference", "FieldObservationOperator"): (
        "a declared field->scalar observation operator, and its own module "
        "docstring calls it a spike. The shape is 2-D BY CONSTRUCTION: a "
        "location is spelled probe_x/probe_y, there is no probe_z, and it "
        "resolves through StructuredMesh.node_index(i, j). Freezing it would "
        "commit the Core to a contract that cannot express an observation of a "
        "3-D field at all -- not a gap that can be filled by adding an "
        "argument, because the frozen spelling would already be wrong"
    ),
    ("engcore.inference", "FieldObservationKind"): (
        "the three kinds -- probe at a location, region mean, field maximum -- "
        "are an obviously partial enumeration of `what scalar do you take from "
        "a field`: no line integral, no flux through a surface, no time window. "
        "Adding a member later is compatible, but this enum is not yet the "
        "considered answer, and freezing it says that it is"
    ),
    ("engcore.inference", "FieldObservationError"): (
        "the error raised by the two above. It descends from "
        "InferenceProblemError, so a caller catching that root still catches "
        "it; what is not frozen is the promise that THIS name keeps existing"
    ),
}

#: Whole modules whose exports are public but NOT frozen, with the reason.
#:
#: ``engcore.studies`` is one flagship study's scaffolding, not a Core
#: contract. It was created in Sprint 8 to orchestrate the linear-TCR
#: calibration example, and everything it exports is specific to that example:
#: ``TcrTruth``, ``tcr_prediction``, ``synthesize_tcr_observations``,
#: ``ols_reference_estimate``. Freezing those would commit the Core to a
#: demonstration's API forever, and a later study would either be stuck with
#: this one's shape or have to break a frozen contract.
#:
#: It stays importable -- the tests use it and it is the worked example the
#: calibration layer is explained through -- but it is marked, so nobody
#: mistakes "it is in the package" for "it is supported".
EXPERIMENTAL_MODULES = {
    "engcore.studies": (
        "one flagship study's scaffolding (linear-TCR calibration), not a Core "
        "contract; freezing it would commit the Core to a demonstration's API"
    ),
}

_PARAMETER_KIND = {
    inspect.Parameter.POSITIONAL_ONLY: "positional_only",
    inspect.Parameter.POSITIONAL_OR_KEYWORD: "positional_or_keyword",
    inspect.Parameter.VAR_POSITIONAL: "var_positional",
    inspect.Parameter.KEYWORD_ONLY: "keyword_only",
    inspect.Parameter.VAR_KEYWORD: "var_keyword",
}


def _render_default(value: Any) -> Any:
    """A default rendered so that two processes agree, byte for byte.

    ``repr`` is not usable: for anything without a stable ``__repr__`` it
    embeds a memory address, so the snapshot would differ between runs of
    identical code. Values whose identity is structural are rendered
    structurally; everything else is rendered as its TYPE plus a marker, which
    records "there is a default of this type here" without pretending to
    describe a value that cannot be described canonically.
    """
    if value is inspect.Parameter.empty:
        return {"kind": "none"}
    if isinstance(value, float) and (value != value or value in (_INF, -_INF)):
        # A NON-FINITE DEFAULT, rendered as a name rather than as a number.
        #
        # Two reasons, and the first is the one the repository already enforces
        # everywhere else: `json.dumps` emits NaN and Infinity as the bare
        # tokens `NaN` and `Infinity`, which no conforming JSON reader accepts
        # -- `serialization.unwritable` refuses exactly this in a scientific
        # record, and a snapshot claiming to be canonical JSON must not do what
        # the records are forbidden from doing.
        #
        # The second is that `nan != nan`, so a raw NaN in the snapshot makes
        # the pinned-vs-current comparison fail against an IDENTICAL API. That
        # is how this was found.
        name = "nan" if value != value else ("inf" if value > 0 else "-inf")
        return {"kind": "literal", "type": "float", "non_finite": name}
    if value is None or isinstance(value, (bool, int, float, str)):
        # bool before int matters for the type name, and json handles the rest.
        return {"kind": "literal", "type": type(value).__name__, "value": value}
    if isinstance(value, enum.Enum):
        return {"kind": "enum", "type": type(value).__name__, "member": value.name}
    if isinstance(value, (tuple, frozenset)):
        return {"kind": "immutable_container", "type": type(value).__name__,
                "size": len(value)}
    if isinstance(value, (list, dict, set)):
        # A MUTABLE default is worth flagging in the snapshot itself, not only
        # in a review: it is the classic shared-state bug, and freezing one
        # would freeze the bug.
        return {"kind": "MUTABLE_DEFAULT", "type": type(value).__name__,
                "size": len(value)}
    if value is dataclasses.MISSING:
        return {"kind": "none"}
    return {"kind": "object", "type": type(value).__name__}


def _signature_of(value: Any) -> dict[str, Any] | None:
    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError):
        return None
    parameters = []
    for name, parameter in signature.parameters.items():
        parameters.append({
            "name": name,
            "kind": _PARAMETER_KIND[parameter.kind],
            "has_default": parameter.default is not inspect.Parameter.empty,
            "default": _render_default(parameter.default),
        })
    return {
        "parameters": parameters,
        "required": [
            p["name"] for p in parameters
            if not p["has_default"] and p["kind"] not in ("var_positional", "var_keyword")
        ],
    }


def _factory_name(factory: Any) -> str | None:
    """A dataclass default factory, identified without running it.

    ``module:qualname`` rather than ``repr``, which for a class embeds a memory
    address and would make the snapshot non-deterministic. Returns None when
    there is no factory, which is the common case.
    """
    if factory is dataclasses.MISSING:
        return None
    module = getattr(factory, "__module__", "?")
    name = getattr(factory, "__qualname__", None) or getattr(
        factory, "__name__", type(factory).__name__
    )
    return f"{module}:{name}"


def _dataclass_fields(value: Any) -> list[dict[str, Any]] | None:
    if not (inspect.isclass(value) and dataclasses.is_dataclass(value)):
        return None
    # Declaration order, NOT sorted: for a dataclass the order IS the
    # positional-construction contract, so sorting here would hide a reorder.
    return [
        {
            "name": field.name,
            "has_default": field.default is not dataclasses.MISSING
            or field.default_factory is not dataclasses.MISSING,  # type: ignore[misc]
            "default": _render_default(field.default),
            "has_default_factory": field.default_factory is not dataclasses.MISSING,  # type: ignore[misc]
            # WHICH factory, not merely that there is one. `has_default_factory`
            # alone is a hole: changing `default_factory=tuple` to
            # `default_factory=list` changes what every caller who omits the
            # argument receives -- mutable instead of immutable, a different
            # type in an isinstance check -- and would not move the frozen
            # digest. Recorded STATICALLY by name rather than by calling the
            # factory: taking a snapshot must not execute package code.
            "default_factory": _factory_name(field.default_factory),
            "init": field.init,
        }
        for field in dataclasses.fields(value)
    ]


def _enum_members(value: Any) -> list[dict[str, Any]] | None:
    if not (inspect.isclass(value) and issubclass(value, enum.Enum)):
        return None
    # Definition order: an enum's member order is part of its contract for
    # iteration, and a reorder is a change worth failing on.
    return [{"name": member.name, "value": member.value} for member in value]


def _exception_bases(value: Any) -> list[str] | None:
    if not (inspect.isclass(value) and issubclass(value, BaseException)):
        return None
    # The full MRO by qualified name, so a base swapped anywhere in the chain
    # is visible -- `except SomeBase` is a contract a caller writes against.
    return [
        f"{klass.__module__}.{klass.__qualname__}"
        for klass in value.__mro__
        if klass is not object
    ]


def _union_members(value: Any) -> list[str] | None:
    """Member type names of a union alias, sorted, or ``None``.

    Sorted because ``A | B`` and ``B | A`` are the same type and must produce
    the same snapshot; qualified so two same-named classes from different
    modules do not collapse.
    """
    import typing

    origin = typing.get_origin(value)
    import types as _types

    if origin is not typing.Union and not isinstance(value, _types.UnionType):
        return None
    return sorted(
        f"{getattr(arg, '__module__', '?')}.{getattr(arg, '__qualname__', repr(arg))}"
        for arg in typing.get_args(value)
    )


def _kind_of(value: Any) -> str:
    if inspect.isclass(value):
        if issubclass(value, BaseException):
            return "exception"
        if issubclass(value, enum.Enum):
            return "enum"
        if dataclasses.is_dataclass(value):
            return "dataclass"
        return "class"
    if inspect.isfunction(value) or inspect.isbuiltin(value):
        return "function"
    if isinstance(value, (str, int, float, bool, tuple, frozenset)):
        return "constant"
    return type(value).__name__


def describe(module_name: str, name: str, value: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "module": module_name,
        "name": name,
        "kind": _kind_of(value),
        "classification": "FREEZE",
    }
    why = EXPERIMENTAL_MODULES.get(module_name) or EXPERIMENTAL_SYMBOLS.get(
        (module_name, name)
    )
    if why is not None:
        entry["classification"] = "EXPERIMENTAL"
        entry["experimental_because"] = why

    # DEPRECATED overrides FREEZE but never EXPERIMENTAL: deprecating something
    # that was never promised is not a compatibility event, and saying so would
    # imply the Core had made a promise it is now withdrawing.
    record = DEPRECATED_SYMBOLS.get((module_name, name))
    if record is not None and entry["classification"] == "FREEZE":
        entry["classification"] = "DEPRECATED"
        entry["deprecation"] = {
            "reason": record["reason"],
            "replacement": record["replacement"],
            "category": record["category"].__name__,
            "since": record["since"],
            "removal": record["removal"],
        }

    # A type alias is a contract too: `ScientificValue` naming a different set
    # of types is a change every annotation against it inherits. Recorded by
    # MEMBER NAME rather than by repr, which would otherwise carry module paths
    # and vary with how the union was spelled.
    alias_members = _union_members(value)
    if alias_members is not None:
        entry["union_members"] = alias_members
    # `__module__` is where the object is DEFINED; `module` above is where it is
    # exported from. Both are recorded: a symbol that starts being re-exported
    # from somewhere else keeps its canonical path, and one whose definition
    # moves is visible here.
    defined_in = getattr(value, "__module__", None)
    if defined_in:
        entry["defined_in"] = defined_in

    signature = _signature_of(value)
    if signature is not None:
        entry["signature"] = signature
        for parameter in signature["parameters"]:
            key = f"{module_name}:{name}:{parameter['name']}"
            if key in EXPERIMENTAL_PARAMETERS:
                parameter["classification"] = "EXPERIMENTAL"

    fields = _dataclass_fields(value)
    if fields is not None:
        entry["dataclass_fields"] = fields
    members = _enum_members(value)
    if members is not None:
        entry["enum_members"] = members
    bases = _exception_bases(value)
    if bases is not None:
        entry["exception_mro"] = bases
    if entry["kind"] == "constant":
        entry["value"] = _render_default(value)
    return entry


def build(*, modules: tuple[str, ...] = CANONICAL_MODULES) -> dict[str, Any]:
    """The whole public surface -- frozen AND experimental -- canonically ordered.

    Both populations are described, because a change to an experimental symbol
    should still be VISIBLE. They are kept in separate digests so that
    visibility never turns into a promise: see :func:`frozen_digest`.

    ``modules`` defaults to the V1 canonical modules, so the V1 snapshot is
    unchanged; pass :data:`V2_CANONICAL_MODULES` for the Core V2 surface.
    """
    modules = tuple(modules)
    unknown = [m for m in modules if m not in V2_CANONICAL_MODULES]
    if unknown:
        raise ValueError(f"not a canonical Core module: {unknown}")
    symbols = []
    for module_name in modules:
        module = importlib.import_module(module_name)
        for name in sorted(getattr(module, "__all__", ()) or ()):
            symbols.append(describe(module_name, name, getattr(module, name)))
    symbols.sort(key=lambda entry: (entry["module"], entry["name"]))
    frozen = [e for e in symbols if e["classification"] == "FREEZE"]
    experimental = [e for e in symbols if e["classification"] != "FREEZE"]
    return {
        "schema": SCHEMA,
        "modules": list(modules),
        "symbol_count": len(symbols),
        "frozen_count": len(frozen),
        "experimental_count": len(experimental),
        "symbols": symbols,
    }


def frozen_only(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """The FROZEN surface alone -- the compatibility contract.

    Experimental symbols are excluded rather than merely labelled, so that
    adding, changing or removing one cannot move the frozen digest. If they
    shared a digest, every edit to the `engcore.studies` example would look
    like a compatibility event, and the day somebody stopped believing the
    alarm is the day a real one goes unnoticed.
    """
    payload = build() if snapshot is None else snapshot
    # DEPRECATED is IN. Deprecation says a contract will end, not that it has
    # ended -- and a symbol that left the frozen surface on being deprecated
    # could then be REMOVED without moving the frozen digest, which is the one
    # event this digest exists to catch.
    frozen = [
        e for e in payload["symbols"]
        if e["classification"] in ("FREEZE", "DEPRECATED")
    ]
    return {
        "schema": SCHEMA,
        "contract": "frozen",
        "symbol_count": len(frozen),
        "symbols": frozen,
    }


def canonical_bytes(snapshot: dict[str, Any] | None = None) -> bytes:
    """The snapshot as bytes two processes must agree on exactly."""
    payload = build() if snapshot is None else snapshot
    # `allow_nan=False` is the guard, not a formality: without it a non-finite
    # default anywhere in the API would silently emit the tokens `NaN` or
    # `Infinity`, and the "canonical JSON" this function promises would be
    # unreadable by a conforming parser. `_render_default` converts non-finite
    # floats to names before they reach here; this raises if one ever slips
    # past, rather than writing a file nobody can read back.
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def digest(snapshot: dict[str, Any] | None = None) -> str:
    """Digest of the WHOLE surface, frozen and experimental together."""
    return hashlib.sha256(canonical_bytes(snapshot)).hexdigest()


def frozen_digest(snapshot: dict[str, Any] | None = None) -> str:
    """Digest of the frozen contract alone. This is the compatibility number."""
    return hashlib.sha256(canonical_bytes(frozen_only(snapshot))).hexdigest()


if __name__ == "__main__":  # pragma: no cover - a tool entry point
    import sys

    surface = V2_CANONICAL_MODULES if "--v2" in sys.argv else CANONICAL_MODULES
    if "--frozen-digest" in sys.argv:
        print(frozen_digest(build(modules=surface)))
    elif "--digest" in sys.argv:
        print(digest(build(modules=surface)))
    else:
        # PRETTY, not canonical. The pinned files exist to be READ in review --
        # a one-line 345 kB blob is not reviewable, and a contract nobody can
        # read is not a contract. Nothing is lost: every comparison in the test
        # suite runs through `canonical_bytes`, so the on-disk formatting
        # cannot drift a check and cannot fake a pass either. The two --digest
        # flags above stay canonical, because those ARE the bytes.
        full = build(modules=surface)
        payload = frozen_only(full) if "--frozen" in sys.argv else full
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True,
                          allow_nan=False)
        # Written as bytes with explicit LF: on Windows a text-mode write turns
        # every newline into CRLF, and these files are byte-pinned elsewhere.
        sys.stdout.buffer.write((text + chr(10)).encode("utf-8"))
