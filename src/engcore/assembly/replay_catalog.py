"""Golden replay baselines for production multiphysics authority.

Golden scenarios contain literal independently-derived outputs. They do not
derive their expected values from Forge's current runtime, so they can detect a
scientific regression rather than merely replaying the implementation under
test.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping

from .multiphysics import AuthorizedMultiphysicsRun
from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity
from ..scientific.verification.adjudication import VerificationDecision

GOLDEN_REPLAY_INPUT_SCHEMA = "forge.golden_replay_input/1"
GOLDEN_REPLAY_OUTPUT_SCHEMA = "forge.golden_replay_output/1"
GOLDEN_REPLAY_SCENARIO_SCHEMA = "forge.golden_replay_scenario/1"


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, order=True)
class GoldenReplayInput:
    fact_path: str
    value: Quantity

    def __post_init__(self) -> None:
        path = str(self.fact_path).strip()
        if not path or not isinstance(self.value, Quantity):
            raise InvalidScientificProblem(
                "golden replay input requires fact_path and Quantity value"
            )
        object.__setattr__(self, "fact_path", path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GOLDEN_REPLAY_INPUT_SCHEMA,
            "fact_path": self.fact_path,
            "value": self.value.to_dict(),
        }


@dataclass(frozen=True, order=True)
class GoldenReplayOutput:
    quantity: str
    run_output_key: str
    expected: Quantity
    tolerance: Quantity

    def __post_init__(self) -> None:
        quantity = str(self.quantity).strip()
        key = str(self.run_output_key).strip()
        if not quantity or not key:
            raise InvalidScientificProblem(
                "golden replay output requires quantity and run_output_key"
            )
        if not isinstance(self.expected, Quantity) or not isinstance(
            self.tolerance, Quantity
        ):
            raise InvalidScientificProblem(
                "golden replay output requires Quantity expected/tolerance"
            )
        converted = self.tolerance.to(self.expected.units)
        if converted.magnitude < 0.0:
            raise InvalidScientificProblem(
                "golden replay output tolerance must be non-negative"
            )
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "run_output_key", key)
        object.__setattr__(self, "tolerance", converted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GOLDEN_REPLAY_OUTPUT_SCHEMA,
            "quantity": self.quantity,
            "run_output_key": self.run_output_key,
            "expected": self.expected.to_dict(),
            "tolerance": self.tolerance.to_dict(),
        }


@dataclass(frozen=True)
class GoldenReplayScenario:
    scenario_id: str
    capability_id: str
    composition_pack_id: str
    composition_pack_version: str
    execution_pack_id: str
    execution_pack_version: str
    start: Quantity
    end: Quantity
    inputs: tuple[GoldenReplayInput, ...]
    outputs: tuple[GoldenReplayOutput, ...]
    reference_basis: str
    composition_manifest_digest: str = ""
    execution_manifest_digest: str = ""

    def __post_init__(self) -> None:
        for label in (
            "scenario_id",
            "capability_id",
            "composition_pack_id",
            "composition_pack_version",
            "execution_pack_id",
            "execution_pack_version",
            "reference_basis",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"golden replay scenario requires {label}"
                )
            object.__setattr__(self, label, value)
        if not isinstance(self.start, Quantity) or not isinstance(
            self.end, Quantity
        ):
            raise InvalidScientificProblem(
                "golden replay scenario start/end must be time Quantities"
            )
        start = self.start.to("second")
        end = self.end.to("second")
        if end.magnitude <= start.magnitude:
            raise InvalidScientificProblem(
                "golden replay scenario end must be after start"
            )
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

        inputs = tuple(sorted(self.inputs))
        if not inputs:
            raise InvalidScientificProblem(
                "golden replay scenario requires inputs"
            )
        input_paths = [item.fact_path for item in inputs]
        if len(input_paths) != len(set(input_paths)):
            raise InvalidScientificProblem(
                "golden replay scenario contains duplicate fact paths"
            )
        object.__setattr__(self, "inputs", inputs)

        outputs = tuple(
            sorted(self.outputs, key=lambda item: item.quantity)
        )
        if not outputs:
            raise InvalidScientificProblem(
                "golden replay scenario requires expected outputs"
            )
        quantities = [item.quantity for item in outputs]
        keys = [item.run_output_key for item in outputs]
        if len(quantities) != len(set(quantities)) or len(keys) != len(
            set(keys)
        ):
            raise InvalidScientificProblem(
                "golden replay scenario output identities must be unique"
            )
        object.__setattr__(self, "outputs", outputs)

        for label in (
            "composition_manifest_digest",
            "execution_manifest_digest",
        ):
            digest = str(getattr(self, label)).strip().lower()
            if digest and (
                len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)
            ):
                raise InvalidScientificProblem(
                    f"golden replay {label} must be empty or SHA-256"
                )
            object.__setattr__(self, label, digest)

    @property
    def key(self) -> str:
        return self.scenario_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GOLDEN_REPLAY_SCENARIO_SCHEMA,
            "scenario_id": self.scenario_id,
            "capability_id": self.capability_id,
            "composition_pack_id": self.composition_pack_id,
            "composition_pack_version": self.composition_pack_version,
            "composition_manifest_digest": self.composition_manifest_digest,
            "execution_pack_id": self.execution_pack_id,
            "execution_pack_version": self.execution_pack_version,
            "execution_manifest_digest": self.execution_manifest_digest,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "reference_basis": self.reference_basis,
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True)
class GoldenReplayComparison:
    quantity: str
    observed: Quantity | None
    expected: Quantity
    tolerance: Quantity
    absolute_error: Quantity | None
    passed: bool
    problem: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.passed, bool):
            raise InvalidScientificProblem(
                "golden replay comparison passed must be bool"
            )


@dataclass(frozen=True)
class GoldenReplayVerification:
    scenario_id: str
    passed: bool
    comparisons: tuple[GoldenReplayComparison, ...]
    problems: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.scenario_id).strip():
            raise InvalidScientificProblem(
                "golden replay verification requires scenario_id"
            )
        object.__setattr__(self, "comparisons", tuple(self.comparisons))
        object.__setattr__(
            self,
            "problems",
            tuple(str(item) for item in self.problems),
        )


class GoldenReplayCatalog:
    def __init__(
        self,
        scenarios: Iterable[GoldenReplayScenario] = (),
    ) -> None:
        self._items: dict[str, GoldenReplayScenario] = {}
        for scenario in scenarios:
            if not isinstance(scenario, GoldenReplayScenario):
                raise TypeError(
                    "GoldenReplayCatalog accepts GoldenReplayScenario only"
                )
            if scenario.key in self._items:
                raise InvalidScientificProblem(
                    f"duplicate golden replay scenario {scenario.key!r}"
                )
            self._items[scenario.key] = scenario

    def get(self, scenario_id: str) -> GoldenReplayScenario:
        try:
            return self._items[str(scenario_id)]
        except KeyError:
            raise InvalidScientificProblem(
                f"unknown golden replay scenario {scenario_id!r}"
            ) from None

    def list(self) -> tuple[GoldenReplayScenario, ...]:
        return tuple(self._items[key] for key in sorted(self._items))

    def for_composition(
        self,
        pack_id: str,
        pack_version: str,
    ) -> tuple[GoldenReplayScenario, ...]:
        return tuple(
            item
            for item in self.list()
            if (
                item.composition_pack_id,
                item.composition_pack_version,
            )
            == (str(pack_id), str(pack_version))
        )


def _same_quantity(left: Quantity, right: Quantity) -> bool:
    try:
        return left.to(right.units).magnitude == right.magnitude
    except Exception:
        return False


def verify_golden_replay(
    authorized: AuthorizedMultiphysicsRun,
    scenario: GoldenReplayScenario,
) -> GoldenReplayVerification:
    """Verify an executed authorized run against one immutable golden case."""

    if not isinstance(authorized, AuthorizedMultiphysicsRun):
        raise TypeError("verify_golden_replay requires AuthorizedMultiphysicsRun")
    if not isinstance(scenario, GoldenReplayScenario):
        raise TypeError("verify_golden_replay requires GoldenReplayScenario")

    problems: list[str] = []
    plan = authorized.graph_plan

    for label, observed, expected in (
        ("capability_id", plan.capability_id, scenario.capability_id),
        (
            "composition_pack_id",
            plan.authority_pack_id,
            scenario.composition_pack_id,
        ),
        (
            "composition_pack_version",
            plan.authority_pack_version,
            scenario.composition_pack_version,
        ),
        (
            "execution_pack_id",
            plan.execution_pack_id,
            scenario.execution_pack_id,
        ),
        (
            "execution_pack_version",
            plan.execution_pack_version,
            scenario.execution_pack_version,
        ),
    ):
        if observed != expected:
            problems.append(
                f"{label} mismatch: observed={observed!r}, expected={expected!r}"
            )

    if (
        scenario.composition_manifest_digest
        and authorized.composition_snapshot.manifest_digest
        != scenario.composition_manifest_digest
    ):
        problems.append("composition manifest digest differs from golden authority")
    if (
        scenario.execution_manifest_digest
        and authorized.execution_snapshot.manifest_digest
        != scenario.execution_manifest_digest
    ):
        problems.append("execution manifest digest differs from golden authority")

    coupling_plan = plan.coupling_plan
    if coupling_plan is None:
        problems.append("GraphPlan has no coupling plan")
    else:
        if not _same_quantity(coupling_plan.time.start, scenario.start):
            problems.append("coupling start differs from golden scenario")
        if not _same_quantity(coupling_plan.time.end, scenario.end):
            problems.append("coupling end differs from golden scenario")

    actual_inputs = {
        item.fact_path: item.value for item in plan.external_inputs
    }
    expected_paths = {item.fact_path for item in scenario.inputs}
    if set(actual_inputs) != expected_paths:
        problems.append(
            "golden input paths differ: "
            f"observed={sorted(actual_inputs)}, expected={sorted(expected_paths)}"
        )
    for item in scenario.inputs:
        observed = actual_inputs.get(item.fact_path)
        if not isinstance(observed, Quantity):
            problems.append(
                f"golden input {item.fact_path!r} is missing or not Quantity"
            )
            continue
        if not _same_quantity(observed, item.value):
            problems.append(
                f"golden input {item.fact_path!r} value differs"
            )

    if not authorized.system_validation or not all(
        item.result.valid for item in authorized.system_validation
    ):
        problems.append("authorized run did not pass all system validation")
    if not authorized.system_verification or not all(
        item.run.result.complete
        and item.run.result.verification.decision
        is VerificationDecision.VERIFIED
        for item in authorized.system_verification
    ):
        problems.append(
            "authorized run did not pass all independent verification routes"
        )

    comparisons: list[GoldenReplayComparison] = []
    for expected_output in scenario.outputs:
        raw = authorized.run.final_outputs.get(
            expected_output.run_output_key
        )
        if raw is None:
            problem = (
                f"missing final output {expected_output.run_output_key!r}"
            )
            problems.append(problem)
            comparisons.append(
                GoldenReplayComparison(
                    quantity=expected_output.quantity,
                    observed=None,
                    expected=expected_output.expected,
                    tolerance=expected_output.tolerance,
                    absolute_error=None,
                    passed=False,
                    problem=problem,
                )
            )
            continue
        try:
            observed = Quantity.from_dict(raw).to(
                expected_output.expected.units
            )
            error = Quantity(
                abs(
                    (observed - expected_output.expected).magnitude_in(
                        expected_output.expected.units
                    )
                ),
                expected_output.expected.units,
            )
            passed = (
                error.magnitude
                <= expected_output.tolerance.to(
                    expected_output.expected.units
                ).magnitude
            )
            problem = "" if passed else (
                f"{expected_output.quantity} differs by {error}, tolerance "
                f"{expected_output.tolerance}"
            )
            if problem:
                problems.append(problem)
            comparisons.append(
                GoldenReplayComparison(
                    quantity=expected_output.quantity,
                    observed=observed,
                    expected=expected_output.expected,
                    tolerance=expected_output.tolerance,
                    absolute_error=error,
                    passed=passed,
                    problem=problem,
                )
            )
        except Exception as exc:
            problem = (
                f"cannot decode/compare {expected_output.quantity}: "
                f"{type(exc).__name__}: {exc}"
            )
            problems.append(problem)
            comparisons.append(
                GoldenReplayComparison(
                    quantity=expected_output.quantity,
                    observed=None,
                    expected=expected_output.expected,
                    tolerance=expected_output.tolerance,
                    absolute_error=None,
                    passed=False,
                    problem=problem,
                )
            )

    return GoldenReplayVerification(
        scenario_id=scenario.scenario_id,
        passed=not problems and all(item.passed for item in comparisons),
        comparisons=tuple(comparisons),
        problems=tuple(problems),
    )


def builtin_golden_replay_catalog() -> GoldenReplayCatalog:
    """Return literal production baselines pinned to current built-in manifests."""

    # Local imports keep catalog definitions out of Composition/Execution pack
    # initialization and avoid making scientific provider modules depend on
    # assembly/release tooling.
    from ..compositionpacks.builtin_electrothermal_feedback import (
        MANIFEST as FEEDBACK_COMPOSITION,
    )
    from ..compositionpacks.builtin_thermal_resistance import (
        MANIFEST as THERMAL_RESISTANCE_COMPOSITION,
    )
    from ..executionpacks.builtin_electrothermal_feedback import (
        MANIFEST as FEEDBACK_EXECUTION,
    )
    from ..executionpacks.builtin_thermal_resistance import (
        MANIFEST as THERMAL_RESISTANCE_EXECUTION,
    )

    one_way = GoldenReplayScenario(
        scenario_id="thermal_resistance.nominal_v1",
        capability_id="system.thermal_resistance_property",
        composition_pack_id=THERMAL_RESISTANCE_COMPOSITION.pack_id,
        composition_pack_version=THERMAL_RESISTANCE_COMPOSITION.pack_version,
        composition_manifest_digest=THERMAL_RESISTANCE_COMPOSITION.digest,
        execution_pack_id=THERMAL_RESISTANCE_EXECUTION.pack_id,
        execution_pack_version=THERMAL_RESISTANCE_EXECUTION.pack_version,
        execution_manifest_digest=THERMAL_RESISTANCE_EXECUTION.digest,
        start=Quantity(0.0, "second"),
        end=Quantity(100.0, "second"),
        inputs=(
            GoldenReplayInput(
                "thermal.heat_capacity",
                Quantity(100.0, "joule/kelvin"),
            ),
            GoldenReplayInput(
                "thermal.ambient_conductance",
                Quantity(2.0, "watt/kelvin"),
            ),
            GoldenReplayInput(
                "thermal.ambient_temperature",
                Quantity(300.0, "kelvin"),
            ),
            GoldenReplayInput(
                "thermal.initial_temperature",
                Quantity(300.0, "kelvin"),
            ),
            GoldenReplayInput(
                "thermal.heat_input",
                Quantity(10.0, "watt"),
            ),
            GoldenReplayInput(
                "conductor.reference_resistance",
                Quantity(10.0, "ohm"),
            ),
            GoldenReplayInput(
                "conductor.temperature_coefficient",
                Quantity(0.004, "1/kelvin"),
            ),
            GoldenReplayInput(
                "conductor.reference_temperature",
                Quantity(300.0, "kelvin"),
            ),
        ),
        outputs=(
            GoldenReplayOutput(
                "final_temperature",
                "thermal.temperature",
                Quantity(304.32332358381694, "kelvin"),
                Quantity(1e-8, "kelvin"),
            ),
            GoldenReplayOutput(
                "resistance",
                "material.resistance",
                Quantity(10.172932943352677, "ohm"),
                Quantity(1e-8, "ohm"),
            ),
        ),
        reference_basis=(
            "Literal closed-form first-order thermal response followed by the "
            "linear-TCR constitutive relation; values were derived outside the "
            "Forge multiphysics runtime."
        ),
    )

    feedback = GoldenReplayScenario(
        scenario_id="electrothermal_feedback.nominal_v1",
        capability_id="system.electrothermal_feedback",
        composition_pack_id=FEEDBACK_COMPOSITION.pack_id,
        composition_pack_version=FEEDBACK_COMPOSITION.pack_version,
        composition_manifest_digest=FEEDBACK_COMPOSITION.digest,
        execution_pack_id=FEEDBACK_EXECUTION.pack_id,
        execution_pack_version=FEEDBACK_EXECUTION.pack_version,
        execution_manifest_digest=FEEDBACK_EXECUTION.digest,
        start=Quantity(0.0, "second"),
        end=Quantity(100.0, "second"),
        inputs=(
            GoldenReplayInput(
                "thermal.heat_capacity",
                Quantity(100.0, "joule/kelvin"),
            ),
            GoldenReplayInput(
                "thermal.ambient_conductance",
                Quantity(2.0, "watt/kelvin"),
            ),
            GoldenReplayInput(
                "thermal.ambient_temperature",
                Quantity(300.0, "kelvin"),
            ),
            GoldenReplayInput(
                "thermal.initial_temperature",
                Quantity(300.0, "kelvin"),
            ),
            GoldenReplayInput(
                "material.reference_resistance",
                Quantity(10.0, "ohm"),
            ),
            GoldenReplayInput(
                "material.temperature_coefficient",
                Quantity(0.004, "1/kelvin"),
            ),
            GoldenReplayInput(
                "material.reference_temperature",
                Quantity(300.0, "kelvin"),
            ),
            GoldenReplayInput(
                "electrical.source_voltage",
                Quantity(10.0, "volt"),
            ),
        ),
        outputs=(
            GoldenReplayOutput(
                "final_temperature",
                "thermal.temperature",
                Quantity(304.2654056020089, "kelvin"),
                Quantity(1e-3, "kelvin"),
            ),
            GoldenReplayOutput(
                "resistance",
                "material.resistance",
                Quantity(10.170616224080355, "ohm"),
                Quantity(3e-4, "ohm"),
            ),
            GoldenReplayOutput(
                "heat_generation",
                "electrical.heat_generation",
                Quantity(9.832245932477132, "watt"),
                Quantity(3e-4, "watt"),
            ),
        ),
        reference_basis=(
            "Literal high-accuracy monolithic electrothermal ODE reference "
            "integrated independently with DOP853; the expected values are "
            "not generated from the staggered Forge coupling runtime."
        ),
    )

    return GoldenReplayCatalog((one_way, feedback))


__all__ = [
    "GOLDEN_REPLAY_INPUT_SCHEMA",
    "GOLDEN_REPLAY_OUTPUT_SCHEMA",
    "GOLDEN_REPLAY_SCENARIO_SCHEMA",
    "GoldenReplayCatalog",
    "GoldenReplayComparison",
    "GoldenReplayInput",
    "GoldenReplayOutput",
    "GoldenReplayScenario",
    "GoldenReplayVerification",
    "builtin_golden_replay_catalog",
    "verify_golden_replay",
]
