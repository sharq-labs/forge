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
design -- that is how "a missing declaration yields UNKNOWN and never
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

Where the rule lives now, and why it moved
-------------------------------------------
This module used to *be* the guard, and four domains called it. The fifth --
``electrical/dc`` -- did not, so a parameter named
``dissipated_power_utilization`` still bought IN_DOMAIN from a resistor with no
rating declared at all. That is the shape of the real defect: not one domain
that got it wrong, but a core that permitted the mistake and five domains each
obliged to remember not to make it.

So the rule is now in the core, and cannot be declined:

* ``ValidityDomain.derived_quantities`` names the reserved set, **on the model
  record**, so a registry can enumerate every reserved name in the repository
  and a new domain is covered the day it registers.
* ``ScientificModelDefinition`` refuses to be constructed if a validity
  condition reads a name that is neither a declared input nor reserved. A
  derived quantity cannot be introduced unreserved -- the module will not
  import.
* ``ValidityDomain.assess`` takes the two namespaces separately and refuses a
  merged mapping carrying a reserved name. There is no signature through which
  the old ``update`` mistake can still be written.
* ``ScientificProblem.validity_context`` requires the reserved set and refuses
  a parameter that occupies one of its names.

What is left here
-----------------
The **assembler's** namespace, which is wider than any one model's. A domain
reserves two kinds of name. The derived groups its conditions read, which the
core now owns; and the state coordinates it injects because the core's
parameter-built context structurally cannot reach them -- ``cell_temperature``,
``temperature``, ``discharge_current``. The second kind is often read by no
condition at all: it is what the *derivations* are computed from. A caller
parameter occupying one of those would decide a whole family of derived groups
at once without any condition ever reading it directly, so it must be kept out
of the declared context too, and only the domain knows which names those are.

:class:`DomainValidityContext` carries the pair and hands each model exactly
the slice that model reserves, so one assembly can serve four models that
reserve four different subsets of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ..scientific.errors import InvalidScientificProblem

__all__ = [
    "DomainValidityContext",
    "assembler_namespace",
    "caller_declared",
    "assembled_validity_context",
]


def assembler_namespace(
    models: Iterable[Any], *, state_coordinates: Iterable[str] = ()
) -> frozenset[str]:
    """Every name a domain's assembler owns, derived from its own models.

    The union of what the models reserve -- read off the records rather than
    restated beside them -- plus the state coordinates the assembler injects,
    which no condition reads directly and which therefore cannot be discovered
    from a model. A domain that adds a model gets that model's reserved names
    here without anyone editing a list.
    """
    reserved: set[str] = set(state_coordinates)
    for model in models:
        reserved |= set(model.derived_quantities)
    return frozenset(reserved)


def caller_declared(
    context: Mapping[str, Any], reserved: Iterable[str]
) -> dict[str, Any]:
    """The caller's own context, with every reserved name removed.

    Still needed for the *state coordinates*.
    ``ScientificProblem.validity_context`` now refuses a parameter carrying a
    reserved name outright, so nothing reaches here with a forged derived group
    in it. What this still does is strip a name a domain injects but no
    condition reads, which the core cannot see and so cannot refuse; and it is
    what the derivations themselves are handed, so a forged value cannot be
    read as an *input* to a derivation either.
    """
    reserved = frozenset(reserved)
    return {
        name: value for name, value in context.items() if name not in reserved
    }


@dataclass(frozen=True)
class DomainValidityContext:
    """One domain's assembly, in the two namespaces a model is assessed over.

    ``declared`` is the caller's, already free of every reserved name.
    ``assembled`` is what this domain computed and injected. They stay apart
    all the way to ``assess``, because merging them is the defect: a type that
    cannot represent the merge is how this stops being a thing to remember.

    :meth:`assess` hands a model **only the assembled names that model
    reserves**. A domain assembles once for every model it serves, and the four
    battery models reserve four different subsets of one assembly; handing the
    whole of it to each would trip the core's own "assembled but not reserved"
    refusal over names that are simply another model's business.
    """

    declared: Mapping[str, Any]
    assembled: Mapping[str, Any]

    def assess(self, model: Any) -> Any:
        """This model's verdict, over the slice of the assembly it reserves."""
        reserved = model.derived_quantities
        return model.assess_validity(
            declared=self.declared,
            assembled={
                name: value
                for name, value in self.assembled.items()
                if name in reserved
            },
        )

    def merged(self) -> dict[str, Any]:
        """Both namespaces in one mapping, for inspection and reporting only.

        Never for assessment. A condition reading this could not tell which
        half a value came from, which is the whole defect; what reads it is a
        test asking what was assembled, or a report quoting a derived number
        back to a human.
        """
        return {**self.declared, **self.assembled}

    # A read-only mapping view, so a caller that only wants to look at one
    # derived number does not have to know about the split. Assessment does
    # not go through here -- ``assess`` above takes the two halves directly.
    def __getitem__(self, name: str) -> Any:
        return self.merged()[name]

    def __contains__(self, name: object) -> bool:
        return name in self.declared or name in self.assembled

    def __iter__(self):
        return iter(self.merged())

    def __len__(self) -> int:
        return len(self.merged())

    def keys(self):
        return self.merged().keys()

    def values(self):
        return self.merged().values()

    def items(self):
        return self.merged().items()

    def get(self, name: str, default: Any = None) -> Any:
        return self.merged().get(name, default)


def assembled_validity_context(
    *,
    declared: Mapping[str, Any],
    assembled: Mapping[str, Any],
    reserved: Iterable[str],
) -> DomainValidityContext:
    """The two namespaces a validity domain is assessed against.

    ``declared`` must already have been through :func:`caller_declared` -- it
    is the caller's parameters minus the assembler's namespace. ``assembled``
    is what this domain actually produced: the groups it could derive, and the
    state coordinates it was given. ``reserved`` is the namespace the domain
    owns, from :func:`assembler_namespace`.

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
    return DomainValidityContext(
        declared=dict(declared), assembled=dict(assembled)
    )
