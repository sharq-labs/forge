"""The numbers a verification gate judges against, as a record with identity.

The defect
----------
A caller who can set the tolerance a verification is judged against has defeated
the verification. Both refinement gates in this repository took their thresholds
as ordinary keyword arguments::

    run_verification_gate(run, invariant_rel_tol=1e-3)   # awards the same level

The domain's own number was the *default*, which is the weakest possible
statement of ownership: the level awarded, the report's prose, the provenance
record and every downstream consumer read exactly the same whether the gate ran
against the declared threshold or against one the caller invented on the way in.
The only trace was the number itself, in a field a reader had to know to check.

This is not the same defect as a caller forging a derived quantity, and it is
worse in one respect. A forged quantity at least has to be *supplied*; a
threshold override arrives through the sanctioned parameter of a public
function and looks like configuration.

The rule
--------
**A threshold that gates an evidentiary level belongs to the domain that awards
it, and a set that is not the domain's own awards nothing.**

Not "awards a weaker level" and not "awards it with a warning". There is no
level in :class:`ValidationLevel` that means *converged, against a number the
caller chose*, and inventing one would put the reader back where they started —
holding a level and having to go and check what it was measured against.

So a gate takes a :class:`VerificationThresholds` rather than a float, and
:meth:`VerificationThresholds.award` returns ``None`` for a set that is not
declared. The comparison still runs, the residual is still reported, the detail
still says what happened and by how much: everything a caller exploring a
tolerance actually wants is still there. What is withheld is the *claim*, which
is the one thing that was never theirs to set.

Why versioned rather than simply removed
-----------------------------------------
The round offered both. Removing the parameter would make a threshold
unchangeable, and that is worse than it sounds: exploring how a gate behaves
against a tighter number is a legitimate and useful thing to do, and a domain
that forbids it pushes the work into a fork of the gate where nobody sees it.

Versioning keeps the exploration and takes away only its authority.
:meth:`derive` produces a set whose identity says, in the record, that it is an
override of a named declared set and which values were changed. That identity
travels into every check's ``evidence``, so a report is self-describing: a
reader looking at a passing check can see which threshold set it was judged
against without knowing anything about how the gate was called.

Authority is verified, never supplied
-------------------------------------
``derived_from`` marks the overrides :meth:`derive` makes, and for a while an
empty one was all "declared" meant. It is caller-controlled: anybody could build
``VerificationThresholds(gate_id=<a real gate>, version=<its version>,
values=<looser numbers>)`` and receive the level that gate's own numbers award.
The name of a gate is public, and it was never proof of anything.

So a set is **declared** only when the core verifies it against the declaration
the domain layer pins for its gate: ``SCIENTIFIC_THRESHOLD_DECLARATIONS`` on the
package that holds the domains, mapping each ``gate_id`` to the declaring
constant, its ``version`` and the SHA-256 of its values. The check runs at
promotion, on every call, over the record's own fields: the gate must be
registered, the version must be the registered one, and :attr:`threshold_digest`
recomputed from the values must be the registered digest. Anything else is a
threshold *specification* -- every comparison still runs against it and every
residual is still reported -- and it awards nothing.

Nothing a caller passes and nothing a payload carries can say "declared". There
is no such field; a serialized ``fingerprint`` is checked against the values
rather than read; and the type cannot be subclassed to answer
:attr:`is_declared` for itself. The core knows the attribute name and nothing
more: which gates exist, and what their numbers are, the domain layer states.

What this does not do
---------------------
It cannot make a *future* gate use it. A domain that writes a gate taking bare
floats has the original defect back, and the core has no way to refuse a
function signature it never sees. ``tests/test_core_guards.py`` checks the
repository for that instead, and ``NEEDS.md`` records what a real lock would
require.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import ScientificValidationError
from ..serialization import require_schema, schema_string
from .immutable import freeze
from .validation import ValidationLevel

THRESHOLDS_SCHEMA = schema_string("verification_thresholds")

__all__ = ["VerificationThresholds", "THRESHOLDS_SCHEMA"]

#: The attribute the core reads the domain layer's pinned declarations from.
#: The core knows this name and the package it lives on, never a gate.
THRESHOLD_DECLARATIONS_ATTRIBUTE = "SCIENTIFIC_THRESHOLD_DECLARATIONS"
_DECLARING_PACKAGE = f"{__name__.split('.')[0]}.domains"


@dataclass(frozen=True)
class VerificationThresholds:
    """One named, versioned set of numbers a gate judges against.

    ``gate_id`` and ``version`` name the set. ``values`` are the numbers.
    ``basis`` says where they came from — preregistered, declared after
    exploratory analysis, taken from a standard — and is not decoration: a
    reader weighing a level needs it, and one gate in this repository spends
    four paragraphs of its own module docstring on exactly that.

    ``derived_from`` is empty for a domain's declared set and carries the
    declared set's identity for an override. That is the whole mechanism: an
    override is a different record, says so, and awards nothing.
    """

    gate_id: str
    version: str
    values: Mapping[str, float]
    basis: str = ""
    derived_from: str = ""

    def __post_init__(self) -> None:
        for label in ("gate_id", "version"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise ScientificValidationError(
                    f"verification thresholds require a non-empty {label}"
                )
            object.__setattr__(self, label, text)
        if not self.values:
            raise ScientificValidationError(
                f"verification thresholds {self.gate_id!r} declare no values; "
                f"a gate with no numbers judges nothing"
            )
        cleaned: dict[str, float] = {}
        for name, value in self.values.items():
            number = float(value)
            # NaN would make every comparison silently false and infinity would
            # make every one silently true. Either turns a gate into a rubber
            # stamp in the direction of its own sign, so both are refused here
            # rather than by whichever comparison happens to read them first.
            if number != number or number in (float("inf"), float("-inf")):
                raise ScientificValidationError(
                    f"verification threshold {name!r} of {self.gate_id!r} is "
                    f"{value!r}; a non-finite threshold makes every comparison "
                    f"against it unconditionally true or unconditionally false"
                )
            cleaned[str(name)] = number
        # FROZEN, not merely copied. `frozen=True` protects the attribute and
        # not the object behind it, so `thresholds.values[k] = v` was accepted
        # on every threshold set this platform has ever produced -- on the one
        # record whose entire purpose is to be the number a gate cannot be
        # talked out of.
        #
        # The mutation was not academic. It moved `fingerprint`, so the
        # evidence line a report carries described numbers the gate had not
        # been judged against; and it left `derived_from` empty, so `award`
        # went on granting the level that `derive` exists to withhold. A caller
        # who could not widen a tolerance through the sanctioned path could
        # widen it through the mapping and keep the claim.
        object.__setattr__(self, "values", freeze(dict(sorted(cleaned.items()))))
        object.__setattr__(self, "derived_from", str(self.derived_from).strip())

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError(
            "VerificationThresholds cannot be subclassed: a subclass could "
            "answer is_declared or award for itself, and authority is the one "
            "thing a threshold set may not answer for itself"
        )

    # ---- identity -------------------------------------------------------
    @property
    def identity(self) -> str:
        return f"{self.gate_id}@{self.version}"

    @property
    def threshold_digest(self) -> str:
        """SHA-256 over the values, recomputed on every read.

        The number the domain layer pins for a declared gate. Recomputed rather
        than remembered, so a set whose values were changed after it was built
        is judged by the values it holds now.
        """
        blob = json.dumps(dict(self.values), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @property
    def fingerprint(self) -> str:
        """SHA-256 over the values, so two sets with the same name differ visibly."""
        return self.threshold_digest[:16]

    @property
    def is_declared(self) -> bool:
        """Is this a declared gate's own set, as the core verifies it?

        Not a field and not an input -- see :func:`_verified_against_declaration`.
        An override, an unregistered gate, another version or other numbers are
        all threshold specifications, and award nothing.
        """
        return _verified_against_declaration(self)

    def __getitem__(self, name: str) -> float:
        try:
            return self.values[name]
        except KeyError:
            raise ScientificValidationError(
                f"verification thresholds {self.identity} declare no {name!r}; "
                f"available: {sorted(self.values)}"
            ) from None

    def __contains__(self, name: object) -> bool:
        return name in self.values

    # ---- derivation -----------------------------------------------------
    def derive(self, **overrides: float) -> "VerificationThresholds":
        """The same gate at different numbers, marked as not the domain's.

        Every overridden name must already exist: a gate judges against the
        numbers it was written to judge against, and inventing a new one here
        would be inventing a criterion the gate does not read.
        """
        unknown = sorted(set(overrides) - set(self.values))
        if unknown:
            raise ScientificValidationError(
                f"verification thresholds {self.identity} have no {unknown}; "
                f"deriving a threshold this gate does not read would add a "
                f"criterion nothing evaluates. Available: {sorted(self.values)}"
            )
        changed = {
            name: float(value)
            for name, value in overrides.items()
            if float(value) != self.values[name]
        }
        if not changed:
            # Nothing actually moved. This is the same set, and calling it an
            # override would withhold a level from a caller who changed nothing.
            return self
        merged = {**self.values, **changed}
        marker = hashlib.sha256(
            json.dumps(merged, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:12]
        return VerificationThresholds(
            gate_id=self.gate_id,
            version=f"{self.version}+override.{marker}",
            values=merged,
            basis=(
                f"caller override of {self.identity} on "
                f"{sorted(changed)}; not the declared gate"
            ),
            derived_from=self.identity,
        )

    # ---- what a gate is allowed to claim --------------------------------
    def award(
        self, level: ValidationLevel, *, earned: bool
    ) -> ValidationLevel | None:
        """The level, if the comparison passed **and** these are the domain's numbers.

        ``earned`` is the gate's own verdict on the comparison. This method adds
        the second condition, which is the guard: a threshold set the caller
        supplied cannot buy the level its declared counterpart would have. The
        gate still reports the comparison, the residual and the detail — only
        the claim is withheld, because the claim is the part that was never the
        caller's to make.
        """
        if not earned:
            return None
        if not self.is_declared:
            return None
        return ValidationLevel(level)

    def evidence(self) -> tuple[str, ...]:
        """What a check should record about the numbers it was judged against.

        Goes into ``ValidationCheck.evidence``, so a report says which threshold
        set produced its levels without a reader having to know how the gate was
        called. An override says so in its own identity.
        """
        entries = [f"thresholds:{self.identity}#{self.fingerprint}"]
        if self.derived_from:
            entries.append(f"thresholds-override-of:{self.derived_from}")
        entries.extend(
            f"threshold:{name}={value:.6g}"
            for name, value in sorted(self.values.items())
        )
        return tuple(entries)

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": THRESHOLDS_SCHEMA,
            "gate_id": self.gate_id,
            "version": self.version,
            "values": dict(self.values),
            "basis": self.basis,
            "derived_from": self.derived_from,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "VerificationThresholds":
        require_schema(payload, THRESHOLDS_SCHEMA)
        record = cls(
            gate_id=payload["gate_id"],
            version=payload["version"],
            values=dict(payload.get("values", {})),
            basis=payload.get("basis", ""),
            derived_from=payload.get("derived_from", ""),
        )
        # A serialized fingerprint is a claim about the values beside it, so it
        # is checked against them rather than believed. It confers nothing
        # either way -- authority is re-verified at promotion -- but a payload
        # whose numbers and fingerprint disagree was edited, and is refused.
        claimed = payload.get("fingerprint")
        if claimed is not None and claimed != record.fingerprint:
            raise ScientificValidationError(
                f"serialized verification thresholds {record.identity} carry "
                f"fingerprint {claimed!r}, but their values give "
                f"{record.fingerprint!r}; a threshold record whose numbers and "
                f"fingerprint disagree was altered after it was written"
            )
        return record


def _declarations() -> Mapping[str, Any]:
    """The domain layer's pinned declarations, or none if it states none."""
    try:
        package = importlib.import_module(_DECLARING_PACKAGE)
    except ImportError:  # pragma: no cover - an installation without its domains
        return {}
    table = getattr(package, THRESHOLD_DECLARATIONS_ATTRIBUTE, None)
    return table if isinstance(table, Mapping) else {}


def _verified_against_declaration(thresholds: VerificationThresholds) -> bool:
    """Whether ``thresholds`` is a declared gate's own set. Fails closed at each step.

    A function over the record's fields rather than a method the record could
    answer, for the reason ``validation.level_is_earned`` gives. Every step reads
    the domain layer's pin and nothing the caller or a payload asserted:

    1. a set that says it overrides another is not that declaration;
    2. the gate must be registered -- a public name is not a declaration;
    3. the version must be the registered version;
    4. the values must hash to the registered digest.
    """
    if thresholds.derived_from:
        return False
    declared = _declarations().get(thresholds.gate_id)
    if not isinstance(declared, Mapping):
        return False
    if thresholds.version != declared.get("version"):
        return False
    if thresholds.threshold_digest != declared.get("threshold_digest"):
        return False
    return True
