"""Evidence identity: which computation a piece of evidence belongs to.

THE DEFECT THIS EXISTS TO CLOSE
--------------------------------
Every trust record in this corpus was checkable on its *contents* and
uncheckable on its *provenance*. A validation envelope full of supported cells
could be handed to any authorized run. Numerical evidence naming a producer
could be handed to a run that producer never touched. A replay outcome could be
handed to a different run as long as one string matched. In each case the
evidence was real -- it simply belonged to something else, and nothing in the
record said so.

They are one defect, so they get one primitive. An :class:`EvidenceBinding` is
a set of role-tagged authority components: which model, which realization,
which solver, which parameter set, which pack authority, which graph, which
run. Evidence carries one; a computation derives one; certification asks
whether the evidence's binding is satisfied by the computation's.

WHAT MATCHING MEANS, AND WHY IT IS ONE-DIRECTIONAL
---------------------------------------------------
Evidence is usually *narrower* than a computation. A validation campaign may be
about one model and one realization, while a run is about a whole graph, its
packs and its plan. So the rule is containment, not equality: **every component
the evidence names must appear identically in the computation's binding.**

A role the evidence names and the computation does not is a mismatch, not a
pass. Fail-closed here means an unrecognised claim is a refusal: evidence that
says "this is about model X" cannot be accepted by a computation that cannot
say which model it used.

THIS IS BINDING, NOT AUTHENTICATION
------------------------------------
A digest here proves that two records refer to the same authority, not that a
trusted party produced them. Anyone who can call the constructor can write any
binding they like, and no amount of hashing changes that -- the trust boundary
is which code calls certification, not which code can build a dataclass. What
binding does buy is the thing actually being got wrong: evidence produced for
one computation can no longer be *borrowed* by another, because the two
bindings will not agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Iterable, Mapping

from ..serialization import require_schema, schema_string
from .source import CorpusError, text

AUTHORITY_COMPONENT_SCHEMA = schema_string("corpus_authority_component")
EVIDENCE_BINDING_SCHEMA = schema_string("corpus_evidence_binding")


class AuthorityRole(str, Enum):
    """What kind of authority a component names.

    Deliberately the vocabulary this repository already uses. Core learns no
    domain here: a role says *what kind of thing* an identifier refers to, never
    what the thing is for.
    """

    MODEL = "model"
    REALIZATION = "realization"
    SOLVER = "solver"
    ADAPTER = "adapter"
    PARAMETER_SET = "parameter_set"
    DATASET = "dataset"
    COMPOSITION_PACK = "composition_pack"
    EXECUTION_PACK = "execution_pack"
    DOMAIN_PACK = "domain_pack"
    BLUEPRINT = "blueprint"
    GRAPH = "graph"
    COUPLING_PLAN = "coupling_plan"
    SCENARIO = "scenario"
    RUN = "run"
    PRODUCER = "producer"
    POLICY = "policy"


@dataclass(frozen=True, order=True)
class AuthorityComponent:
    """One authority: its role, its identity, its version and its digest.

    ``version`` and ``digest`` are optional because not every authority in this
    repository carries both, but whatever is stated is part of identity: a
    component naming a digest matches only a component naming the same digest.
    """

    role: AuthorityRole
    identifier: str
    version: str = ""
    digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", AuthorityRole(self.role))
        object.__setattr__(self, "identifier", text(self.identifier, label="identifier"))
        object.__setattr__(self, "version", str(self.version).strip())
        digest = str(self.digest).strip().lower()
        if digest and (
            len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise CorpusError(
                f"authority component {self.identifier!r} digest must be sha256 hex"
            )
        object.__setattr__(self, "digest", digest)

    @property
    def key(self) -> tuple[str, str, str]:
        return self.role.value, self.identifier, self.version

    def describe(self) -> str:
        version = f"@{self.version}" if self.version else ""
        digest = f" ({self.digest[:12]}...)" if self.digest else ""
        return f"{self.role.value}:{self.identifier}{version}{digest}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": AUTHORITY_COMPONENT_SCHEMA,
            "role": self.role.value,
            "identifier": self.identifier,
            "version": self.version,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AuthorityComponent":
        require_schema(payload, AUTHORITY_COMPONENT_SCHEMA)
        return cls(
            AuthorityRole(payload["role"]),
            payload["identifier"],
            payload.get("version", ""),
            payload.get("digest", ""),
        )


@dataclass(frozen=True)
class EvidenceBinding:
    """The scientific authority a piece of evidence belongs to.

    Immutable, deterministically serialized and digestible, so two records can
    be compared by digest when they should be identical and by
    :meth:`mismatches` when one is allowed to be narrower.
    """

    binding_id: str
    components: tuple[AuthorityComponent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_id", text(self.binding_id, label="binding_id"))
        components = tuple(sorted(self.components))
        if not components:
            raise CorpusError(
                "an evidence binding names no authority at all; evidence that "
                "cannot say what it is about cannot be checked against anything"
            )
        if any(not isinstance(item, AuthorityComponent) for item in components):
            raise CorpusError("evidence binding requires AuthorityComponent records")
        keys = [item.key for item in components]
        if len(keys) != len(set(keys)):
            raise CorpusError(
                "evidence binding names one authority twice; an identity is one "
                "statement"
            )
        object.__setattr__(self, "components", components)

    def component(self, role: AuthorityRole) -> AuthorityComponent | None:
        wanted = AuthorityRole(role)
        for item in self.components:
            if item.role is wanted:
                return item
        return None

    def roles(self) -> tuple[str, ...]:
        return tuple(sorted({item.role.value for item in self.components}))

    def mismatches(self, computation: "EvidenceBinding") -> tuple[str, ...]:
        """Why this evidence does not belong to that computation. Empty means it does.

        Containment, not equality: every component named here must appear
        identically there. A role this evidence names and the computation does
        not is a mismatch -- fail-closed, because a computation that cannot say
        which model it used cannot accept evidence claiming to be about one.
        """
        if not isinstance(computation, EvidenceBinding):
            raise CorpusError("an evidence binding is compared against another binding")
        found = {item.key: item for item in computation.components}
        by_role: dict[str, list[AuthorityComponent]] = {}
        for item in computation.components:
            by_role.setdefault(item.role.value, []).append(item)

        problems: list[str] = []
        for item in self.components:
            exact = found.get(item.key)
            if exact is None:
                present = by_role.get(item.role.value, ())
                if not present:
                    problems.append(
                        f"the computation names no {item.role.value} authority, so "
                        f"it cannot accept evidence bound to {item.describe()}"
                    )
                else:
                    problems.append(
                        f"evidence is bound to {item.describe()} but the "
                        f"computation uses "
                        f"{', '.join(sorted(x.describe() for x in present))}"
                    )
                continue
            if item.digest and exact.digest != item.digest:
                problems.append(
                    f"evidence is bound to {item.describe()} but the computation's "
                    f"{item.role.value} digest is {exact.digest[:12]}..."
                )
        return tuple(problems)

    def is_satisfied_by(self, computation: "EvidenceBinding") -> bool:
        return not self.mismatches(computation)

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EVIDENCE_BINDING_SCHEMA,
            "binding_id": self.binding_id,
            "components": [item.to_dict() for item in self.components],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceBinding":
        require_schema(payload, EVIDENCE_BINDING_SCHEMA)
        return cls(
            payload["binding_id"],
            tuple(AuthorityComponent.from_dict(i) for i in payload["components"]),
        )

    @classmethod
    def of(
        cls, binding_id: str, components: Iterable[AuthorityComponent]
    ) -> "EvidenceBinding":
        return cls(binding_id, tuple(components))


def require_binding(value: object, *, label: str) -> EvidenceBinding:
    if not isinstance(value, EvidenceBinding):
        raise CorpusError(f"{label} requires an EvidenceBinding")
    return value


__all__ = [
    "AUTHORITY_COMPONENT_SCHEMA",
    "EVIDENCE_BINDING_SCHEMA",
    "AuthorityComponent",
    "AuthorityRole",
    "EvidenceBinding",
    "require_binding",
]
