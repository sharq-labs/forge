"""Recursively immutable containers for scientific records, and detached payloads.

``@dataclass(frozen=True)`` protects the **attribute**, not the object behind
it. Every record in this package is frozen and every one of them was mutable::

    provenance.inputs["injected"] = 5        # accepted
    result.values["injected"] = 5            # accepted — and a bare int, which
                                             # the constructor refuses outright
    result.to_dict()["metadata"]["a"]["b"] = 9   # mutates the record itself

The last one is the worst of the three, because it needs no intent. ``to_dict``
built a fresh outer dict and then handed out the *same nested objects* the
record holds, so a caller who serialized a record and edited the payload — the
ordinary thing to do with a payload — silently rewrote the record it came from.
Provenance, validation and values are the platform's evidence; evidence that
edits itself when a reader touches its own serialized form is not evidence.

The two guarantees
------------------
**Internal state is recursively immutable.** Mappings become
:class:`FrozenMapping`, lists become :class:`FrozenList`, sets become
:class:`FrozenSet`, tuples keep their type — and in every case the *contents*
are frozen too, so there is no depth at which mutation becomes possible again.
A bare number cannot be injected into ``values`` after construction, because
``values`` cannot be written to at all.

Each of these is a subclass of the built-in it replaces, so a record's field
still equals, prints, serializes and ``isinstance``-checks as what it was. That
is not cosmetic: these mappings are handed to ``json.dumps`` and splatted with
``{**m}`` throughout the repository, and a stricter type that broke those would
have traded a working platform for a tidier class diagram.

**``to_dict`` returns a recursively detached payload.** Nothing in the returned
structure is shared with the record, at any depth, so the payload is a caller's
to keep and edit. That is the right direction to fix it in: a payload is a
message, and messages are supposed to be editable — it is the record that must
not move.

What this is not
----------------
It is not tamper-proofing, and this package has never claimed to be. Anyone
willing to call ``object.__setattr__`` can rewrite a frozen record anywhere in
this repository, and ``FrozenMapping`` keeps its contents in an attribute that
the same call reaches. The guarantee is against *accident and ordinary use*:
mutation now requires deliberately reaching around the type system, rather than
being what a normal dict subscript or a normal payload edit happens to do.

Nor is it deep-copy-on-read. ``freeze`` shares immutable leaves — a
``Quantity``, a string, a frozen dataclass — rather than copying them, so
freezing a record costs about what the defensive ``dict(...)`` copies it
replaces cost, and reading is free.

Cost
----
Measured; see the TASK 5 commit message. Construction pays one extra shallow
pass over each mapping it already copied. ``to_dict`` pays a detach of the
free-form fields — ``metadata``, ``tolerances``, ``environment`` and a
declaration's ``payload`` — which are small, and of nothing else, because every
other branch of a payload is built out of freshly created dicts already.
"""

from __future__ import annotations

from collections.abc import Mapping as _RuntimeMapping
from typing import Any, Iterator, Mapping, Sequence
#: ``typing.Mapping`` and ``collections.abc.Mapping`` are the SAME CLASS
#: (``typing.Mapping.__origin__`` IS that class), but an ``isinstance``
#: against the typing alias routes through ``typing.__subclasscheck__`` and
#: measures 2.56x slower here. Annotations keep ``Mapping``; runtime checks
#: use ``_RuntimeMapping``. Same check, same answer, same refusals.


__all__ = [
    "FrozenList",
    "FrozenMapping",
    "FrozenSet",
    "detach",
    "freeze",
]


#: Every name ``dict`` has that ``Mapping`` does not, split into the ones that
#: mutate and the ones that do not. Kept as data rather than as a list of
#: ``def``\ s so a test can assert the split is **complete** against the
#: running interpreter: if a future CPython grows a ``dict`` method, that test
#: fails and somebody classifies it, instead of a new hole opening in silence.
#: This is the checkable form of "overriding all of them is a list somebody
#: will forget to extend".
DICT_MUTATORS = frozenset(
    {
        "__delitem__",
        "__ior__",
        "__setitem__",
        "clear",
        "pop",
        "popitem",
        "setdefault",
        "update",
    }
)

#: ``dict``-only names that do not mutate the receiver. ``copy`` and the two
#: ``|`` operators all return a **new plain dict**, which is exactly what a
#: caller wanting a mutable version should get.
DICT_NON_MUTATORS = frozenset({"__or__", "__ror__", "copy", "fromkeys"})


def _refuse(name):
    def blocked(self, *args, **kwargs):
        raise TypeError(
            f"{type(self).__name__}.{name}() — this mapping belongs to a "
            f"scientific record and is immutable. Build a new record, or call "
            f"copy() for a mutable dict of the same contents"
        )

    blocked.__name__ = name
    blocked.__qualname__ = f"FrozenMapping.{name}"
    return blocked


class FrozenMapping(dict):
    """A read-only ``dict`` whose values are themselves frozen.

    **A ``dict`` subclass, deliberately.** The first version implemented
    ``Mapping`` instead, on the reasoning that not inheriting the mutators is
    safer than overriding them. That is true in isolation and wrong in place:
    a record's mapping is passed to ``json.dumps``, tested with
    ``isinstance(..., dict)`` and splatted with ``{**m}`` all over this
    repository and by consumers of it, and none of those accept a ``Mapping``
    that is not a ``dict``. Fifteen tests in the multirotor study failed on
    exactly that — a study binding read out of a record's metadata and
    serialized directly.

    Trading a working platform for a stricter type would have been the wrong
    call, so the mutators are overridden and the completeness of that list is
    asserted against the interpreter (see :data:`DICT_MUTATORS`) rather than
    trusted.

    What this costs, stated plainly: ``dict.__setitem__(m, k, v)`` reaches past
    the override, exactly as ``object.__setattr__`` reaches past ``frozen=True``
    on every record in this repository. The guarantee here has never been
    tamper-proofing — it is that **ordinary use cannot mutate a record**, and
    ``m[k] = v``, ``m.update(...)``, ``m.pop(...)`` and ``m |= ...`` all raise.

    Equality, ordering, hashing and serialization are ``dict``'s own, so a
    field that became a ``FrozenMapping`` still equals, prints and serializes
    as what it replaced.

    THE DECISION, TAKEN RATHER THAN DEFERRED AGAIN
    ----------------------------------------------
    ``NEEDS.md A2.6`` raised the ``dict``-subclass weakness twice and closed
    both times with "nothing, unless the platform decides it wants the stronger
    guarantee". **The platform has now decided: accept it.** The argument is
    not that the hole is small, it is that closing it would buy nothing:

    1. ``dict.__setitem__(m, k, v)`` and
       ``object.__setattr__(record, field, value)`` are the *same* hole. Every
       frozen record in this repository has the second one and **none of them
       can close it** — it is a property of the language, not of a design
       choice. A container that closed the first would leave the record it sits
       on wide open through the second, so the class of caller it defends
       against does not exist: anyone willing to reach for an unbound
       ``dict`` method is already willing to reach for ``object.__setattr__``
       one level up.

    2. **The platform's answer to that class of caller is already settled, and
       it is not stronger containers.** It is re-applying the rule where a
       value stops being a field and becomes a claim —
       ``ValidationReport._require_every_level_earned`` and
       ``_require_no_check_contradicts_its_numbers`` both exist for precisely
       this, and both say so. Strengthening this type would add a second,
       weaker mechanism answering a question that one already answers better,
       because re-validation catches a tampered record *however* it was
       tampered with.

    3. What a stronger type would cost is not hypothetical: it is the audit of
       every ``json.dumps``, ``isinstance(..., dict)`` and ``{**m}`` in this
       repository and in every consumer of it, for a guarantee that stops one
       of two doors into the same room.

    **What would reopen this.** A consumer that must accept a record's mapping
    from an untrusted process without re-deriving anything from it. That
    consumer does not exist today; if one is written, it needs the stronger
    type *and* re-validation, and the stronger type alone would still not be
    enough. Recorded so the next reader inherits a decision rather than a third
    round of the same question.
    """

    __slots__ = ()

    def __init__(self, data=None) -> None:
        items = (
            data.items()
            if isinstance(data, _RuntimeMapping)
            else dict(data or {}).items()
        )
        # Through ``dict.__init__`` rather than ``self[k] = v``, which the
        # override below refuses — including to this constructor.
        dict.__init__(self, {key: freeze(value) for key, value in items})

    # The mutators, refused. Generated from DICT_MUTATORS so the list that is
    # asserted complete is the same list that is actually installed.
    for _name in sorted(DICT_MUTATORS):
        locals()[_name] = _refuse(_name)
    del _name

    def copy(self) -> dict:
        """A **plain, mutable** dict of the same contents, one level deep.

        ``dict.copy`` on a subclass already returns a plain ``dict``; this only
        says so out loud, because "how do I get a version I can edit" is the
        question this type creates and it deserves an answer in the docstring
        rather than in a stack trace. The values inside stay frozen — use
        :func:`detach` for a copy that is mutable all the way down.
        """
        return dict(self)

    def __reduce__(self):
        # Pickle and deepcopy reconstruct a dict subclass by calling the class
        # and then ``__setitem__``-ing the items in, which this type refuses.
        # Routed through the constructor instead, which re-freezes.
        return (type(self), (dict(self),))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({dict.__repr__(self)})"


class FrozenList(tuple):
    """A frozen list. A ``tuple`` subclass that remembers it was a list.

    Marked rather than plain, so :func:`detach` can hand a payload back a
    ``list`` where the record was given a ``list`` — a payload whose arrays
    silently became tuples would round-trip through JSON identically but stop
    comparing equal to the value that went in, which is a behaviour change
    disguised as a safety fix.

    **A ``tuple`` subclass, where :class:`FrozenMapping` is a ``dict``
    subclass.** The asymmetry is deliberate and was decided by measurement, not
    by symmetry: ``json`` serializes a tuple as an array and nothing in this
    repository requires a record's list-valued metadata to be a ``list``, so
    genuine immutability costs nothing here — where the same choice for
    mappings broke fifteen tests. ``__eq__`` below closes the one gap that
    remains.
    """

    __slots__ = ()

    def __new__(cls, items: Sequence[Any] = ()):
        return super().__new__(cls, (freeze(item) for item in items))

    def __eq__(self, other: Any) -> bool:
        """Equal to the ``list`` it replaced, as well as to a ``tuple``.

        Without this the freeze would be a silent behaviour change: a record's
        ``metadata["tags"]`` would stop equalling the list the caller passed
        in, and every ``== [...]`` comparison in the repository would start
        answering False for a reason that has nothing to do with the values.
        Symmetric, because ``list.__eq__`` returns ``NotImplemented`` against a
        tuple subclass and Python then tries this side.
        """
        if isinstance(other, (list, tuple)):
            return len(self) == len(other) and all(
                mine == theirs for mine, theirs in zip(self, other)
            )
        return NotImplemented

    def __ne__(self, other: Any) -> bool:
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    #: Kept from ``tuple``. Defining ``__eq__`` would otherwise unset it, and a
    #: frozen sequence that cannot be hashed is a strictly worse tuple.
    __hash__ = tuple.__hash__

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self)!r})"

    def __reduce__(self):
        return (type(self), (list(self),))


class FrozenSet(frozenset):
    """A frozen set that remembers it was a ``set``. See :class:`FrozenList`."""

    __slots__ = ()

    def __new__(cls, items=()):
        return super().__new__(cls, (freeze(item) for item in items))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({set(self)!r})"

    def __reduce__(self):
        return (type(self), (set(self),))


#: Types already known to need no freezing, memoized after one full pass.
#:
#: This function runs once per value on every record construction, and the
#: overwhelmingly common value in this platform is a ``Quantity`` — immutable,
#: not a container, and not something the checks below can recognise without
#: reaching the abstract ``Mapping`` check at the bottom, which is the
#: expensive one. Memoizing by exact type turns the steady state into one set
#: lookup. Bounded by the number of distinct types a process ever freezes.
_ATOMIC_TYPES: set[type] = {str, int, float, bool, bytes, type(None)}


def freeze(value: Any) -> Any:
    """Recursively immutable form of ``value``.

    Containers are converted; everything else is returned **unchanged**, which
    is what keeps this cheap. A ``Quantity``, a string, a number, an enum
    member and a frozen dataclass are already immutable for this purpose and
    are shared rather than copied.

    Already-frozen containers are returned as they are, so re-freezing on a
    ``dataclasses.replace`` or a second ``__post_init__`` costs a type check.
    """
    cls = value.__class__
    if cls in _ATOMIC_TYPES:
        return value
    # Exact-type checks first, in frequency order: they are pointer compares,
    # where the ABC checks below are not.
    if cls is FrozenMapping or cls is FrozenList or cls is FrozenSet:
        return value
    if cls is dict:
        return FrozenMapping(value)
    if cls is list:
        return FrozenList(value)
    if isinstance(value, (FrozenMapping, FrozenList, FrozenSet)):
        return value
    if isinstance(value, _RuntimeMapping):
        return FrozenMapping(value)
    if isinstance(value, list):
        return FrozenList(value)
    if isinstance(value, tuple):
        # A tuple is already immutable; only its contents can need freezing.
        # Returned unchanged when none of them did, which keeps a NamedTuple
        # its own type and costs one pass. Compared by **identity**, not by
        # equality: a FrozenMapping compares equal to the dict it replaced, so
        # an equality test here would report "nothing changed" precisely when
        # something had.
        items = [freeze(item) for item in value]
        if all(new is old for new, old in zip(items, value)):
            return value
        return tuple(items)
    if isinstance(value, (set, frozenset)):
        return FrozenSet(value)
    # Nothing matched, so this type needs no freezing and never will.
    _ATOMIC_TYPES.add(cls)
    return value


def detach(value: Any) -> Any:
    """A plain, fully independent copy of ``value``.

    The inverse of :func:`freeze` for the container types, and the identity for
    everything else — including a ``Quantity``, which is immutable and is
    therefore safe to share into a payload.

    ``FrozenList`` becomes a ``list`` and ``FrozenSet`` a ``set``, so a payload
    gets back the shapes it was given. A plain ``tuple`` stays a ``tuple``, for
    the same reason: it is what the record was handed.
    """
    if isinstance(value, FrozenList):
        return [detach(item) for item in value]
    if isinstance(value, FrozenSet):
        return {detach(item) for item in value}
    if isinstance(value, _RuntimeMapping):
        return {key: detach(item) for key, item in value.items()}
    if isinstance(value, list):
        return [detach(item) for item in value]
    if isinstance(value, tuple):
        return tuple(detach(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return {detach(item) for item in value}
    return value
