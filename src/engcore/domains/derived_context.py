"""Assembling a validity context so a caller cannot forge a derived quantity.

Every domain in this repository answers "was this model applicable here?" the
same way: take the problem's own parameters, compute the dimensionless groups
the model's conditions are stated over, and hand the lot to
``ValidityDomain.assess``. The conditions read that mapping **by name**, and
that is where the hazard lives.

The defect this module exists to remove
----------------------------------------
Assembly used to start from every caller parameter and overwrite only the
quantities it managed to derive::

    context = problem.validity_context()
    context.update(derived_quantities(context, ...))   # WRONG

A derivation that could not be performed returns nothing for its key, by
design — that is how "a missing declaration yields UNKNOWN and never
IN_DOMAIN" is implemented, and it is the discipline every derivation module
here follows. But ``update`` only *overwrites*. A caller parameter carrying a
derived quantity's name therefore **survived the failure of the derivation it
was named after** and was read by the condition as though the domain had
computed it.

That is not a missing guard against a hand-edited record. It is the platform's
central guarantee inverted: the one path by which a missing declaration is
supposed to become UNKNOWN instead becomes the path by which a caller asserts
their way to a verdict, and the report says the model was in domain over a
number nobody computed while the declaration it needed is still absent.

The rule
--------
**The assembled names are the assembler's namespace, and a caller parameter
cannot enter it.** Every name a domain assembles — each derived group, and
each state coordinate the assembler injects because the core's
parameter-built context structurally cannot reach it — is *reserved*. Reserved
names are removed from the caller's context before anything is derived, and
the only values that can occupy them afterwards are the ones the assembler
actually produced.

So a failed derivation leaves its key **absent**, not stale and not
caller-supplied, and the condition reaches ``assess`` as UNKNOWN. There is no
ordering, no precedence and no merge policy to get wrong, because the two
namespaces never overlap.

Which of the two sanctioned fixes this is, and why
---------------------------------------------------
The review offered a choice: reject a caller parameter carrying a reserved name
at problem construction, or make it provably unreadable by any condition. This
is the second.

Rejecting at construction would have to happen in
``ScientificProblem.__post_init__``, and universal core would then need to know
the derived-quantity vocabulary of every domain — ``biot_number``,
``peukert_capacity_ratio``, ``reduced_debye_temperature`` — which is exactly
the domain knowledge the core is arranged not to have. It would also refuse a
problem that is perfectly well-formed: a caller may legitimately carry a
parameter called ``biot_number`` for their own purposes, and the platform's
objection is not to its existence but to its being read as evidence.

Unreadability is the stronger property anyway. Rejection would guard the one
door problems are usually built through; this guards the one door conditions
are *read* through, which is where the substitution would have to occur. A
problem assembled by hand, deserialized from a payload, or produced by a future
builder nobody has written yet reaches the same context assembler, and reaches
it with the same result.

What it does not do
-------------------
It does not decide what is derivable, evaluate a condition, or know any
domain's vocabulary: each domain declares its own reserved set and passes it
in. And it refuses to assemble a name the domain did not reserve, so a derived
quantity added without being registered fails loudly at the first assembly
rather than being quietly impersonable from the day it lands.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..scientific.errors import InvalidScientificProblem

__all__ = ["caller_declared", "assembled_validity_context"]


def caller_declared(
    context: Mapping[str, Any], reserved: Iterable[str]
) -> dict[str, Any]:
    """The caller's own context, with every reserved name removed.

    Removed rather than overwritten later: a value that is never in the mapping
    cannot be read if the assembler then fails to supply its own, which is the
    whole point. This is also what the derivations themselves are handed, so a
    forged value cannot be read as an *input* to a derivation either.
    """
    reserved = frozenset(reserved)
    return {
        name: value for name, value in context.items() if name not in reserved
    }


def assembled_validity_context(
    *,
    declared: Mapping[str, Any],
    assembled: Mapping[str, Any],
    reserved: Iterable[str],
) -> dict[str, Any]:
    """The context a validity domain is assessed against.

    ``declared`` must already have been through :func:`caller_declared` — it is
    the caller's parameters minus the reserved namespace. ``assembled`` is what
    this domain actually produced: the groups it could derive, and the state
    coordinates it was given. ``reserved`` is the namespace the domain owns.

    Every assembled name must be reserved. A domain that emits a name it did
    not reserve has a derived quantity a caller could impersonate, and it is
    told so here rather than finding out from a verdict.
    """
    reserved = frozenset(reserved)
    unregistered = sorted(set(assembled) - reserved)
    if unregistered:
        raise InvalidScientificProblem(
            f"this domain assembles {unregistered} without reserving the "
            f"name(s); an assembled quantity that is not reserved can be "
            f"supplied by a caller parameter of the same name and read as "
            f"though this domain had computed it. Add it to the reserved set"
        )
    leaked = sorted(set(declared) & reserved)
    if leaked:
        raise InvalidScientificProblem(
            f"caller-declared context still carries the reserved name(s) "
            f"{leaked}; pass it through caller_declared() first"
        )
    return {**declared, **assembled}
