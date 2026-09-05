"""Model-fidelity relationships — contract only, no validated data in M2.

A **fidelity rung** is a level of physical model approximation: a coarse mesh
against a fine one, a lumped model against a distributed one, a reduced-order
surrogate against the full simulation. The defining property is that the rungs
compute *the same physical quantity to different accuracy*.

A **search strategy** is not a fidelity rung. CMA-ES and stacked_v0301 evaluate
the identical objective exactly; only the search differs. Filing their cost
ratio under fidelity was M2's semantic error, and it is exactly the kind of
error that survives review because the arithmetic is fine. A multi-fidelity
planner reading "strategy A is 5000x cheaper than strategy B" as a fidelity
relationship would conclude it may substitute a cheap approximation, when no
approximation was ever made.

    Strategy cost ratios live in :mod:`strategy_relationships`.

**Status in M2: FIDELITY LEARNING = INSUFFICIENT REAL DATA.** At M2 the
repository contained no genuine low/high-fidelity model pairs, so this module
shipped the contract and the guard with nothing empirically validated behind
them.

**That statement about the repository is now out of date, and the correction
matters more than the original claim.** The frozen thermal experiments built
exactly the ladder M2 said did not exist: one 1D conduction model discretized
at three rungs (coarse 8x10, medium 64x80, reference 512x640 cells x steps),
computing the same quantity at measured terminal errors of roughly 1.7e-02,
1.6e-03 and 3.6e-04. T1 established it, T2 showed across repeated draws that
the coarse rung's bias is systematic rather than a draw artifact, and T3
priced escalation across it.

The contract below needed no change to carry it. T1 registered its three
rungs as :class:`FidelityRung` values and its cost ratios as
``STRUCTURE_TRANSFERABLE`` :class:`ModelFidelityRelationship` values with
``metric="work_proxy_ratio"``, and :func:`fidelity_corpus_status` then
reported a real ladder — with no edit to this module. That is the useful
result: the M2 contract was shaped correctly before there was any data to
shape it against, and the first real ladder fit it as-is.

Two things are deliberately still absent, and neither is an oversight:

* **No ladder is registered here.** The thermal rungs are constructed by the
  experiment at run time, not persisted into a production corpus. Registering
  a frozen experiment's discretization choices as production calibration data
  is not something any evidence asks for.
* **No rung carries a cost or an accuracy field.** Cost is already expressible
  as a relationship ``median_ratio``, which is how T1 recorded it, so a
  per-rung cost field would be redundant rather than missing. Accuracy stays
  ``DOMAIN_OWNED`` by the rule below, and T1 explicitly did not route around
  that: its measured bias lives in the experiment's results, not here.

The consequence for a reader: :func:`fidelity_corpus_status` reports on what
has been *registered*, which is still nothing. It is not a claim that no
fidelity evidence exists in this repository. Since T1, it does.

The guard matters more than the contract: :func:`assert_not_a_strategy_identity`
refuses to let an optimizer name be registered as a fidelity rung, so the
mistake M2.1 is correcting cannot be re-made silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from ...scientific.serialization import require_schema, schema_string

FIDELITY_RELATIONSHIP_SCHEMA = schema_string("sria_model_fidelity_relationship")
FIDELITY_RUNG_SCHEMA = schema_string("sria_model_fidelity_rung")


class FidelityOwnership(str, Enum):
    """Who may assert this fidelity statement."""

    #: Cost/runtime ratios between rungs — computational, transferable.
    STRUCTURE_TRANSFERABLE = "structure_transferable"
    #: Accuracy, discrepancy, "good enough" — Domain Pack and Critic only.
    DOMAIN_OWNED = "domain_owned"


class FidelityDataStatus(str, Enum):
    INSUFFICIENT_REAL_DATA = "insufficient_real_data"
    OBSERVED = "observed"


#: Known search-strategy / optimizer identities in this repository. Registering
#: any of these as a fidelity rung is a category error, not a configuration
#: choice, so it raises.
KNOWN_STRATEGY_IDENTITIES: frozenset[str] = frozenset(
    {
        "cmaes",
        "ngopt",
        "random",
        "sobol",
        "de",
        "stacked",
        "stacked_v0301",
        "stacked_fresh_weights_v034",
        "adaptive_stacked",
        "adaptive_stacked_v033",
        "adaptive_stacked_v034",
        "logei",
        "hybrid",
    }
)


class FidelitySemanticError(Exception):
    """A search strategy was presented as a model-fidelity rung."""


def assert_not_a_strategy_identity(rung_id: str) -> None:
    """Refuse an optimizer identity where a fidelity rung is required."""
    normalized = str(rung_id).strip().lower()
    if normalized in KNOWN_STRATEGY_IDENTITIES:
        raise FidelitySemanticError(
            f"{rung_id!r} is a search strategy, not a model-fidelity rung. "
            f"Strategies compute the same objective exactly and differ only in "
            f"search; fidelity rungs compute the same quantity to different "
            f"accuracy. Use strategy_relationships for algorithm cost ratios."
        )
    # Catch the common near-miss spellings too, e.g. "cmaes_v2".
    for known in sorted(KNOWN_STRATEGY_IDENTITIES):
        if normalized.startswith(f"{known}_") or normalized.startswith(f"{known}-"):
            raise FidelitySemanticError(
                f"{rung_id!r} looks like a variant of the search strategy "
                f"{known!r}; a strategy cannot be a model-fidelity rung"
            )


@dataclass(frozen=True)
class FidelityRung:
    """One level of physical model approximation."""

    rung_id: str
    rank: int
    model_ref: str
    description: str = ""
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        rung_id = str(self.rung_id).strip()
        if not rung_id:
            raise FidelitySemanticError("fidelity rung requires a rung_id")
        assert_not_a_strategy_identity(rung_id)
        if not str(self.model_ref).strip():
            raise FidelitySemanticError(
                f"fidelity rung {rung_id!r} must reference the physical model "
                f"it approximates; a rung without a model is not a fidelity level"
            )
        object.__setattr__(self, "rung_id", rung_id)
        object.__setattr__(self, "rank", int(self.rank))
        object.__setattr__(
            self, "attributes", {str(k): str(v) for k, v in self.attributes.items()}
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIDELITY_RUNG_SCHEMA,
            "rung_id": self.rung_id,
            "rank": self.rank,
            "model_ref": self.model_ref,
            "description": self.description,
            "attributes": dict(sorted(self.attributes.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FidelityRung":
        require_schema(payload, FIDELITY_RUNG_SCHEMA)
        return cls(
            rung_id=payload["rung_id"],
            rank=payload["rank"],
            model_ref=payload["model_ref"],
            description=payload.get("description", ""),
            attributes=payload.get("attributes", {}),
        )


@dataclass(frozen=True)
class ModelFidelityRelationship:
    """An observed computational relationship between two fidelity rungs.

    Cost ratios between rungs are structure-transferable. Accuracy and
    sufficiency are not representable here at all — constructing a
    ``DOMAIN_OWNED`` relationship raises, because M2 must not be the place
    where "the coarse model is good enough" gets asserted.
    """

    low_rung: FidelityRung
    high_rung: FidelityRung
    ownership: FidelityOwnership
    metric: str
    data_status: FidelityDataStatus = FidelityDataStatus.INSUFFICIENT_REAL_DATA
    median_ratio: float | None = None
    paired_observations: int = 0
    model_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "ownership", FidelityOwnership(self.ownership))
        object.__setattr__(self, "data_status", FidelityDataStatus(self.data_status))

        if self.ownership is FidelityOwnership.DOMAIN_OWNED:
            raise FidelitySemanticError(
                "accuracy/sufficiency statements are domain-owned; M2 may not "
                "assert them. Record the observation in a Domain Pack instead"
            )
        if self.low_rung.model_ref != self.high_rung.model_ref:
            raise FidelitySemanticError(
                f"fidelity rungs must approximate the same physical model; got "
                f"{self.low_rung.model_ref!r} and {self.high_rung.model_ref!r}. "
                f"Two different models are not two rungs of one ladder"
            )
        if self.low_rung.rank >= self.high_rung.rank:
            raise FidelitySemanticError(
                "low_rung must rank below high_rung"
            )
        if (
            self.data_status is FidelityDataStatus.OBSERVED
            and self.paired_observations <= 0
        ):
            raise FidelitySemanticError(
                "a relationship marked OBSERVED must carry paired observations"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIDELITY_RELATIONSHIP_SCHEMA,
            "low_rung": self.low_rung.to_dict(),
            "high_rung": self.high_rung.to_dict(),
            "ownership": self.ownership.value,
            "metric": self.metric,
            "data_status": self.data_status.value,
            "median_ratio": self.median_ratio,
            "paired_observations": self.paired_observations,
            "model_ref": self.model_ref,
        }


def fidelity_corpus_status(
    rungs: Iterable[FidelityRung] = (),
) -> dict[str, Any]:
    """Report on whether genuine fidelity data exists. In M2 it does not."""
    rungs = tuple(rungs)
    models = {r.model_ref for r in rungs}
    ladders = {m: sorted(r.rank for r in rungs if r.model_ref == m) for m in models}
    usable = {m: ranks for m, ranks in ladders.items() if len(ranks) >= 2}
    return {
        "rungs_registered": len(rungs),
        "models_with_rungs": len(models),
        "models_with_a_real_ladder": len(usable),
        "status": (
            FidelityDataStatus.OBSERVED.value
            if usable
            else FidelityDataStatus.INSUFFICIENT_REAL_DATA.value
        ),
        "note": (
            "no genuine low/high-fidelity model pairs exist in this repository; "
            "search-strategy cost ratios are NOT fidelity data and live in "
            "strategy_relationships"
        )
        if not usable
        else "",
    }
