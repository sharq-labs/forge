from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .manifest import ScientificRunManifest
from .outputs import OutputComparison,OutputExpectation,OutputObservation,compare_output

RUN_REPLAY_RECORD_SCHEMA=schema_string("scientific_run_replay_record")


@dataclass(frozen=True)
class ManifestReplayVerification:
    verified:bool
    problems:tuple[str,...]


def verify_run_manifest(expected:ScientificRunManifest,actual:ScientificRunManifest)->ManifestReplayVerification:
    problems=[]
    if actual.replay_of_manifest_digest!=expected.digest:
        problems.append("actual run is not bound to the expected manifest digest")
    if expected.profile!=actual.profile:
        problems.append("run manifest profile differs")
    for kind in expected.profile.replay_exact_artifact_kinds:
        expected_items=tuple(a for a in expected.contract_artifacts if a.kind==kind)
        actual_items=tuple(a for a in actual.contract_artifacts if a.kind==kind)
        if expected_items!=actual_items:
            problems.append(f"replay-exact artifact identities differ for kind {kind!r}")
    if expected.environment!=actual.environment:
        problems.append("runtime environment differs")
    if expected.random_seed!=actual.random_seed:
        problems.append("random seed differs")
    if expected.parent_run_id!=actual.parent_run_id or expected.parent_manifest_digest!=actual.parent_manifest_digest:
        problems.append("scientific parent lineage differs")
    return ManifestReplayVerification(not problems,tuple(problems))


@dataclass(frozen=True)
class RunReplayVerification:
    verified:bool
    manifest:ManifestReplayVerification
    output_comparisons:tuple[OutputComparison,...]
    problems:tuple[str,...]


@dataclass(frozen=True)
class RunReplayRecord:
    expected_manifest:ScientificRunManifest
    actual_manifest:ScientificRunManifest
    expectations:tuple[OutputExpectation,...]
    observations:tuple[OutputObservation,...]

    def __post_init__(self)->None:
        if not isinstance(self.expected_manifest,ScientificRunManifest) or not isinstance(self.actual_manifest,ScientificRunManifest):
            raise InvalidScientificProblem("run replay record requires typed ScientificRunManifest records")
        expectations=tuple(self.expectations)
        observations=tuple(self.observations)
        if any(not isinstance(x,OutputExpectation) for x in expectations):
            raise InvalidScientificProblem("run replay expectations must be OutputExpectation records")
        if any(not isinstance(x,OutputObservation) for x in observations):
            raise InvalidScientificProblem("run replay observations must be OutputObservation records")
        object.__setattr__(self,"expectations",expectations)
        object.__setattr__(self,"observations",observations)
        eids=[x.output_id for x in expectations];oids=[x.output_id for x in observations]
        if len(eids)!=len(set(eids)) or len(oids)!=len(set(oids)):
            raise InvalidScientificProblem("replay outputs contain duplicate ids")

    @property
    def verification(self)->RunReplayVerification:
        manifest=verify_run_manifest(self.expected_manifest,self.actual_manifest)
        observations={x.output_id:x for x in self.observations}
        expected_ids={x.output_id for x in self.expectations}
        problems=list(manifest.problems);comparisons=[]
        if not self.expectations:
            problems.append(
                "replay declares no expected outputs; output agreement was not tested"
            )
        missing=sorted(expected_ids-set(observations))
        extra=sorted(set(observations)-expected_ids)
        if missing: problems.append(f"missing replay outputs {missing}")
        if extra: problems.append(f"unexpected replay outputs {extra}")
        for expectation in self.expectations:
            observation=observations.get(expectation.output_id)
            if observation is None: continue
            comparison=compare_output(expectation,observation);comparisons.append(comparison)
            if not comparison.matched:
                problems.append(
                    f"output {expectation.output_id!r} differs beyond declared tolerance"
                    + (f": {comparison.problem}" if comparison.problem else "")
                )
        return RunReplayVerification(not problems,manifest,tuple(comparisons),tuple(problems))

    def to_dict(self)->dict[str,Any]:
        verification=self.verification
        return {"schema":RUN_REPLAY_RECORD_SCHEMA,
                "expected_manifest":self.expected_manifest.to_dict(),
                "actual_manifest":self.actual_manifest.to_dict(),
                "expectations":[x.to_dict() for x in self.expectations],
                "observations":[x.to_dict() for x in self.observations],
                "verification":{"verified":verification.verified,
                    "manifest":{"verified":verification.manifest.verified,
                                "problems":list(verification.manifest.problems)},
                    "output_comparisons":[vars(x) for x in verification.output_comparisons],
                    "problems":list(verification.problems)}}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"RunReplayRecord":
        require_schema(payload,RUN_REPLAY_RECORD_SCHEMA)
        value=cls(ScientificRunManifest.from_dict(payload["expected_manifest"]),
                  ScientificRunManifest.from_dict(payload["actual_manifest"]),
                  tuple(OutputExpectation.from_dict(x) for x in payload.get("expectations",())),
                  tuple(OutputObservation.from_dict(x) for x in payload.get("observations",())))
        if payload.get("verification")!=value.to_dict()["verification"]:
            raise InvalidScientificProblem("serialized run replay verification is forged or stale")
        return value
