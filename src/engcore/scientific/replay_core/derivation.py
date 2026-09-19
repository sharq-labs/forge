from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .identity import ArtifactIdentity

DERIVATION_STEP_SCHEMA = schema_string("scientific_derivation_step")
DERIVATION_GRAPH_SCHEMA = schema_string("scientific_derivation_graph")


@dataclass(frozen=True)
class DerivationStep:
    step_id: str
    operation: str
    inputs: tuple[ArtifactIdentity, ...]
    outputs: tuple[ArtifactIdentity, ...]
    implementation_digest: str
    authority_id: str = ""

    def __post_init__(self) -> None:
        import re

        step_id = str(self.step_id).strip()
        operation = str(self.operation).strip()
        authority = str(self.authority_id).strip()
        digest = str(self.implementation_digest).strip().lower()
        inputs = tuple(
            sorted(
                tuple(self.inputs),
                key=lambda a: (a.kind, a.identifier, a.digest),
            )
        )
        outputs = tuple(
            sorted(
                tuple(self.outputs),
                key=lambda a: (a.kind, a.identifier, a.digest),
            )
        )
        if not step_id or not operation:
            raise InvalidScientificProblem(
                "derivation step requires step_id and operation"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise InvalidScientificProblem(
                "derivation step implementation_digest must be lowercase SHA-256"
            )
        if any(not isinstance(a, ArtifactIdentity) for a in inputs + outputs):
            raise InvalidScientificProblem(
                "derivation step inputs/outputs must be ArtifactIdentity records"
            )
        if not outputs:
            raise InvalidScientificProblem(
                "derivation step must declare at least one output artifact"
            )
        input_keys = {(a.kind, a.identifier, a.digest) for a in inputs}
        output_keys = {(a.kind, a.identifier, a.digest) for a in outputs}
        if input_keys & output_keys:
            raise InvalidScientificProblem(
                "derivation step cannot consume and produce the same artifact identity"
            )
        object.__setattr__(self, "step_id", step_id)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "implementation_digest", digest)
        object.__setattr__(self, "authority_id", authority)
        object.__setattr__(self, "inputs", inputs)
        object.__setattr__(self, "outputs", outputs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DERIVATION_STEP_SCHEMA,
            "step_id": self.step_id,
            "operation": self.operation,
            "inputs": [a.to_dict() for a in self.inputs],
            "outputs": [a.to_dict() for a in self.outputs],
            "implementation_digest": self.implementation_digest,
            "authority_id": self.authority_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DerivationStep":
        require_schema(payload, DERIVATION_STEP_SCHEMA)
        return cls(
            payload["step_id"],
            payload["operation"],
            tuple(
                ArtifactIdentity.from_dict(a)
                for a in payload.get("inputs", ())
            ),
            tuple(
                ArtifactIdentity.from_dict(a)
                for a in payload.get("outputs", ())
            ),
            payload["implementation_digest"],
            payload.get("authority_id", ""),
        )


@dataclass(frozen=True)
class ScientificDerivationGraph:
    run_id: str
    roots: tuple[ArtifactIdentity, ...]
    steps: tuple[DerivationStep, ...]
    terminal_artifacts: tuple[ArtifactIdentity, ...]

    def __post_init__(self) -> None:
        run_id = str(self.run_id).strip()
        roots = tuple(
            sorted(
                tuple(self.roots),
                key=lambda a: (a.kind, a.identifier, a.digest),
            )
        )
        steps = tuple(self.steps)
        terminals = tuple(
            sorted(
                tuple(self.terminal_artifacts),
                key=lambda a: (a.kind, a.identifier, a.digest),
            )
        )
        if not run_id:
            raise InvalidScientificProblem(
                "scientific derivation graph requires run_id"
            )
        if any(not isinstance(a, ArtifactIdentity) for a in roots + terminals):
            raise InvalidScientificProblem(
                "derivation roots/terminals must be ArtifactIdentity records"
            )
        if any(not isinstance(s, DerivationStep) for s in steps):
            raise InvalidScientificProblem(
                "derivation graph steps must be DerivationStep records"
            )
        step_ids = [s.step_id for s in steps]
        if len(step_ids) != len(set(step_ids)):
            raise InvalidScientificProblem(
                "derivation graph contains duplicate step ids"
            )

        root_keys = {
            (a.kind, a.identifier, a.digest): a
            for a in roots
        }
        producers: dict[
            tuple[str, str, str],
            DerivationStep,
        ] = {}
        for step in steps:
            for output in step.outputs:
                key = (output.kind, output.identifier, output.digest)
                if key in root_keys:
                    raise InvalidScientificProblem(
                        "a root artifact cannot also be produced by a derivation step"
                    )
                if key in producers:
                    raise InvalidScientificProblem(
                        f"artifact {key!r} has more than one derivation producer"
                    )
                producers[key] = step

        # Build dependency edges between steps by exact artifact identity.
        dependencies: dict[str, set[str]] = {
            step.step_id: set() for step in steps
        }
        available = set(root_keys) | set(producers)
        for step in steps:
            for artifact in step.inputs:
                key = (artifact.kind, artifact.identifier, artifact.digest)
                if key not in available:
                    raise InvalidScientificProblem(
                        f"derivation step {step.step_id!r} consumes orphan artifact {key!r}"
                    )
                producer = producers.get(key)
                if producer is not None:
                    if producer.step_id == step.step_id:
                        raise InvalidScientificProblem(
                            "derivation step cannot depend on its own output"
                        )
                    dependencies[step.step_id].add(producer.step_id)

        # Cycle detection is independent of tuple ordering.
        visiting: set[str] = set()
        done: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise InvalidScientificProblem(
                    "scientific derivation graph contains a dependency cycle"
                )
            if step_id in done:
                return
            visiting.add(step_id)
            for parent in sorted(dependencies[step_id]):
                visit(parent)
            visiting.remove(step_id)
            done.add(step_id)

        for step_id in sorted(dependencies):
            visit(step_id)

        terminal_keys = {
            (a.kind, a.identifier, a.digest) for a in terminals
        }
        for key in terminal_keys:
            if key not in available:
                raise InvalidScientificProblem(
                    f"terminal artifact {key!r} is absent from roots and derivations"
                )

        # Anything produced but neither consumed nor declared terminal would be
        # invisible provenance.  It is allowed only when it is an intermediate
        # that another step explicitly consumes.
        consumed = {
            (a.kind, a.identifier, a.digest)
            for step in steps
            for a in step.inputs
        }
        dangling_outputs = sorted(
            key
            for key in producers
            if key not in consumed and key not in terminal_keys
        )
        if dangling_outputs:
            raise InvalidScientificProblem(
                f"derivation graph has undeclared terminal outputs {dangling_outputs}"
            )

        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "roots", roots)
        object.__setattr__(self, "steps", steps)
        object.__setattr__(self, "terminal_artifacts", terminals)

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": DERIVATION_GRAPH_SCHEMA,
            "run_id": self.run_id,
            "roots": [a.to_dict() for a in self.roots],
            "steps": [
                step.to_dict()
                for step in sorted(self.steps, key=lambda s: s.step_id)
            ],
            "terminal_artifacts": [
                a.to_dict() for a in self.terminal_artifacts
            ],
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.content_dict(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.content_dict(),
            "derivation_graph_digest": self.digest,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "ScientificDerivationGraph":
        require_schema(payload, DERIVATION_GRAPH_SCHEMA)
        value = cls(
            payload["run_id"],
            tuple(
                ArtifactIdentity.from_dict(a)
                for a in payload.get("roots", ())
            ),
            tuple(
                DerivationStep.from_dict(s)
                for s in payload.get("steps", ())
            ),
            tuple(
                ArtifactIdentity.from_dict(a)
                for a in payload.get("terminal_artifacts", ())
            ),
        )
        if (
            "derivation_graph_digest" in payload
            and payload["derivation_graph_digest"] != value.digest
        ):
            raise InvalidScientificProblem(
                "serialized derivation graph digest is forged or stale"
            )
        return value
