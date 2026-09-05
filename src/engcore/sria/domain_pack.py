"""Domain Pack contract.

A Domain Pack owns the science of one field: what the models are, what the
parameters mean, which quantities are of interest, where the models stop being
valid, and how a problem in that field maps onto *computational* covariates.

It deliberately owns none of the cross-cutting machinery. Research strategy,
the cost model, the failure model and any notion of universal scientific truth
stay outside, for a practical reason: the moment two packs each carry their
own strategy and their own failure model, the platform has no way to compare
them, and "which domain gets to vote" becomes an architectural question
instead of a scientific one.

The boundary is enforced by :func:`validate_domain_pack` rather than described
in prose, because a prose boundary is one refactor away from disappearing.

M1 defines the protocol. It does not ship domains — the electrical DC domain
already in the repository is left untouched, and retrofitting it is deliberately
deferred (see the M1 report).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from ..scientific.serialization import require_schema, schema_string
from .errors import DomainPackContractError
from .signatures import SemanticGuard

FIDELITY_SCHEMA = schema_string("sria_fidelity_level")


@dataclass(frozen=True)
class FidelityLevel:
    """One rung of a domain's fidelity ladder.

    ``rank`` orders rungs from cheapest/coarsest upward. The pack declares the
    ladder; it does not decide when to climb it — that is strategy.
    """

    level_id: str
    rank: int
    description: str = ""
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        level_id = str(self.level_id).strip()
        if not level_id:
            raise DomainPackContractError("fidelity level requires a level_id")
        object.__setattr__(self, "level_id", level_id)
        object.__setattr__(self, "rank", int(self.rank))
        object.__setattr__(
            self,
            "attributes",
            {str(k): str(v) for k, v in self.attributes.items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIDELITY_SCHEMA,
            "level_id": self.level_id,
            "rank": self.rank,
            "description": self.description,
            "attributes": dict(sorted(self.attributes.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FidelityLevel":
        require_schema(payload, FIDELITY_SCHEMA)
        return cls(
            level_id=payload["level_id"],
            rank=payload["rank"],
            description=payload.get("description", ""),
            attributes=payload.get("attributes", {}),
        )


@runtime_checkable
class DomainCriticHook(Protocol):
    """A domain-specific check the Arbiter may consult.

    Returns an assessment; it never admits evidence and never writes belief.
    """

    critic_id: str

    def assess(self, evidence: Any) -> Any:
        ...


@runtime_checkable
class DomainPack(Protocol):
    """What every Domain Pack must provide."""

    pack_id: str
    pack_version: str

    def model_references(self) -> tuple[str, ...]:
        """Model ids/references this pack owns."""

    def parameter_semantics(self) -> Mapping[str, str]:
        """Parameter name -> what it physically means."""

    def qois(self) -> tuple[str, ...]:
        """Quantities of interest this pack can report."""

    def scope(self) -> Any:
        """Validity domain (a core ``ValidityDomain`` or equivalent)."""

    def assumptions(self) -> tuple[str, ...]:
        ...

    def fidelity_ladder(self) -> tuple[FidelityLevel, ...]:
        ...

    def extract_covariates(self, subject: Any) -> Mapping[str, float]:
        """Map a domain problem onto *computational* covariates.

        The returned names describe computational shape (state count,
        stiffness proxy, condition estimate), never physics. This is the
        bridge that lets cost and failure learning transfer between domains.
        """

    def domain_critics(self) -> tuple[DomainCriticHook, ...]:
        ...

    def semantic_terms(self) -> tuple[str, ...]:
        """Vocabulary this pack owns, for calibration-key contamination checks."""


REQUIRED_PACK_METHODS = (
    "model_references",
    "parameter_semantics",
    "qois",
    "scope",
    "assumptions",
    "fidelity_ladder",
    "extract_covariates",
    "domain_critics",
    "semantic_terms",
)

#: Responsibilities a Domain Pack must never take over. Named explicitly so the
#: boundary fails loudly instead of eroding.
FORBIDDEN_PACK_ATTRIBUTES = (
    "research_strategy",
    "propose_actions",
    "cost_model",
    "failure_model",
    "universal_truth",
    "global_truth",
    "cross_domain_vote",
    "rank_actions",
    "utility",
)


def validate_domain_pack(pack: Any) -> None:
    """Structurally verify a pack honours the contract and the boundary."""
    for label in ("pack_id", "pack_version"):
        value = str(getattr(pack, label, "")).strip()
        if not value:
            raise DomainPackContractError(f"domain pack requires {label}")

    missing = [
        name for name in REQUIRED_PACK_METHODS if not callable(getattr(pack, name, None))
    ]
    if missing:
        raise DomainPackContractError(
            f"domain pack {pack.pack_id!r} is missing: {sorted(missing)}"
        )

    overreach = [name for name in FORBIDDEN_PACK_ATTRIBUTES if hasattr(pack, name)]
    if overreach:
        raise DomainPackContractError(
            f"domain pack {pack.pack_id!r} exposes {sorted(overreach)}; research "
            f"strategy, cost, failure modelling and cross-domain arbitration are "
            f"platform responsibilities, not domain ones"
        )


def guard_from_packs(packs: Iterable[Any]) -> SemanticGuard:
    """Collect every pack's vocabulary into a calibration-key guard."""
    terms: list[str] = []
    for pack in packs:
        terms.append(str(getattr(pack, "pack_id", "")))
        terms.extend(str(t) for t in pack.semantic_terms())
    return SemanticGuard(t for t in terms if t)
