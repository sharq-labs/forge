from __future__ import annotations

from ..errors import InvalidScientificProblem
from ..results.provenance import ProvenanceRecord
from .artifact_factory import provenance_artifact
from .derivation import ScientificDerivationGraph
from .manifest import ScientificRunManifest


def bind_derivation_to_run(
    manifest: ScientificRunManifest,
    provenance: ProvenanceRecord,
    derivation: ScientificDerivationGraph,
) -> None:
    if manifest.run_id != provenance.run_id or manifest.run_id != derivation.run_id:
        raise InvalidScientificProblem(
            "manifest, provenance and derivation graph must name the same run"
        )
    expected = provenance_artifact(provenance)
    matches = [
        artifact
        for artifact in manifest.contract_artifacts
        if artifact.kind == "provenance_record"
    ]
    if len(matches) != 1 or matches[0] != expected:
        raise InvalidScientificProblem(
            "run manifest does not bind the exact provenance record"
        )

    manifest_artifacts = {
        (artifact.kind, artifact.identifier, artifact.digest)
        for artifact in manifest.contract_artifacts
    }
    terminal_artifacts = {
        (artifact.kind, artifact.identifier, artifact.digest)
        for artifact in derivation.terminal_artifacts
    }
    missing = terminal_artifacts - manifest_artifacts
    if missing:
        raise InvalidScientificProblem(
            f"derivation terminal artifacts are absent from run manifest: {sorted(missing)}"
        )
