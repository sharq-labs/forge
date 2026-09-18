"""CORE-11 -- evidence sources: simulation is one source class, not the only one.

SRIA's :class:`~engcore.sria.evidence.SourceClass` has four members --
SIMULATION, BENCHMARK, MEASUREMENT, LITERATURE -- and
``IMPLEMENTED_SOURCE_CLASSES`` says only SIMULATION is implemented. The claim
layer must not assume every piece of evidence is a simulation, so evidence is
gathered through one adapter per source class:

* the adapter set is **exactly** ``SourceClass`` -- a new member without an
  adapter fails the registry at import, rather than being silently skipped;
* whether an adapter is implemented is read from SRIA's own
  ``IMPLEMENTED_SOURCE_CLASSES``, never from a second list here;
* an unimplemented source answers with an explicit ``NOT_IMPLEMENTED`` outcome
  naming what it would need. It never produces evidence, never raises, and is
  recorded in the assessment so a reader sees which sources were asked.

Phase 4 implemented the other three (:mod:`.external_evidence`) and flipped SRIA's
flag: each adapter reports PRODUCED only for evidence whose standing is
ADMISSIBLE, and NO_EVIDENCE -- naming every weaker record's reasons -- otherwise.

A note on BENCHMARK. A simulation *compared with* a trusted benchmark is still
SIMULATION evidence -- the benchmark comparison is a validation check inside
its credibility report (NAFEMS T3 earns BENCHMARK_VALIDATED that way). A
BENCHMARK-class record is the published benchmark value itself standing as
evidence about the quantity at the oracle's own conditions; it grants no level.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping

from ..sria.evidence import IMPLEMENTED_SOURCE_CLASSES, SourceClass


class SourceStatus(str, Enum):
    PRODUCED = "produced"
    NO_EVIDENCE = "no_evidence"
    NOT_IMPLEMENTED = "not_implemented"


@dataclass(frozen=True)
class SourceOutcome:
    source_class: SourceClass
    status: SourceStatus
    evidence: Any = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_class": self.source_class.value,
            "status": self.status.value,
            "evidence_record_hash": None if self.evidence is None else self.evidence.record_hash,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EvidenceSourceAdapter:
    """One source class. ``produce(context) -> SourceOutcome`` when implemented."""

    source_class: SourceClass
    produce: Callable[[Mapping[str, Any]], SourceOutcome] | None
    requires: str

    @property
    def implemented(self) -> bool:
        return self.source_class in IMPLEMENTED_SOURCE_CLASSES and self.produce is not None

    def gather(self, context: Mapping[str, Any]) -> SourceOutcome:
        if not self.implemented:
            return SourceOutcome(
                self.source_class,
                SourceStatus.NOT_IMPLEMENTED,
                reason=f"{self.source_class.value} evidence is not implemented: {self.requires}",
            )
        return self.produce(context)


def _simulation(context: Mapping[str, Any]) -> SourceOutcome:
    evidence = context.get("simulation_evidence")
    if evidence is None:
        return SourceOutcome(
            SourceClass.SIMULATION,
            SourceStatus.NO_EVIDENCE,
            reason=context.get("simulation_problem") or "the run produced no evidence for this claim",
        )
    return SourceOutcome(SourceClass.SIMULATION, SourceStatus.PRODUCED, evidence=evidence)


def _external(source: SourceClass) -> Callable[[Mapping[str, Any]], SourceOutcome]:
    def produce(context: Mapping[str, Any]) -> SourceOutcome:
        mine = [a for a in context.get("external_assessments", ()) if a.source_class is source]
        admissible = [a for a in mine if a.standing.value == "admissible" and a.evidence is not None]
        if admissible:
            return SourceOutcome(source, SourceStatus.PRODUCED, evidence=admissible[0].evidence,
                                 reason=f"{len(admissible)} admissible of {len(mine)} offered")
        if not mine:
            return SourceOutcome(source, SourceStatus.NO_EVIDENCE, reason=f"no {source.value} evidence was offered or discovered")
        why = "; ".join(f"{a.standing.value}: {a.reasons[0]['reason']}" for a in mine if a.reasons)
        return SourceOutcome(source, SourceStatus.NO_EVIDENCE, reason=f"none of {len(mine)} is admissible ({why})")

    return produce


_REQUIRES = {
    SourceClass.SIMULATION: "a bound credibility report from the plan's execution",
    SourceClass.BENCHMARK: (
        "an SRIA BENCHMARK implementation and an adapter that states a trusted oracle's observation "
        "as evidence about the QOI at the oracle's own conditions"
    ),
    SourceClass.MEASUREMENT: (
        "an SRIA MEASUREMENT implementation and an ingestion boundary for measured values with their "
        "observation-model uncertainty and data provenance"
    ),
    SourceClass.LITERATURE: (
        "an SRIA LITERATURE implementation and a curated, content-pinned reference registry"
    ),
}

#: One adapter per SRIA source class. Checked at import: a class without an
#: adapter, or an adapter for a class SRIA does not define, is refused.
SOURCE_ADAPTERS: Mapping[SourceClass, EvidenceSourceAdapter] = {
    source: EvidenceSourceAdapter(source, _simulation if source is SourceClass.SIMULATION else _external(source), _REQUIRES[source])
    for source in SourceClass
}
if set(SOURCE_ADAPTERS) != set(SourceClass) or set(_REQUIRES) != set(SourceClass):  # pragma: no cover - import guard
    raise RuntimeError("every SRIA SourceClass needs exactly one evidence-source adapter")


def gather_evidence(context: Mapping[str, Any]) -> tuple[SourceOutcome, ...]:
    """Ask every source class, in SRIA's order. Unimplemented ones answer NOT_IMPLEMENTED."""
    return tuple(SOURCE_ADAPTERS[source].gather(context) for source in SourceClass)


__all__ = [
    "SOURCE_ADAPTERS",
    "EvidenceSourceAdapter",
    "SourceOutcome",
    "SourceStatus",
    "gather_evidence",
]
