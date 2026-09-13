from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# 5. V2 UQ records: frozen dataclasses must be transitively immutable.
replace_once(
    "src/engcore/hybrid_uq/local_gaussian.py",
    "from ..scientific.units.quantity import Quantity\n",
    "from ..scientific.results.immutable import freeze\nfrom ..scientific.units.quantity import Quantity\n",
)
replace_once(
    "src/engcore/hybrid_uq/local_gaussian.py",
    '        object.__setattr__(self, "multistart", tuple(dict(m) for m in self.multistart))\n'
    '        object.__setattr__(self, "thresholds", dict(self.thresholds))\n',
    '        object.__setattr__(self, "multistart", tuple(freeze(dict(m)) for m in self.multistart))\n'
    '        object.__setattr__(self, "thresholds", freeze(dict(self.thresholds)))\n',
)
replace_once(
    "src/engcore/hybrid_uq/router.py",
    "from ..scientific.ir.problem import ModelReference\n",
    "from ..scientific.ir.problem import ModelReference\nfrom ..scientific.results.immutable import freeze\n",
)
replace_once(
    "src/engcore/hybrid_uq/router.py",
    '        object.__setattr__(self, "parameter_names", tuple(self.parameter_names))\n'
    '        object.__setattr__(self, "considered", tuple(dict(c) for c in self.considered))\n',
    '        object.__setattr__(self, "parameter_names", tuple(self.parameter_names))\n'
    '        object.__setattr__(\n'
    '            self, "grid_summary",\n'
    '            None if self.grid_summary is None else freeze(dict(self.grid_summary)),\n'
    '        )\n'
    '        object.__setattr__(self, "considered", tuple(freeze(dict(c)) for c in self.considered))\n',
)

# 6/7. Calibration records: residuals cross the record boundary; spec mappings
# are actually immutable, not merely attributes of a frozen dataclass.
replace_once(
    "src/engcore/inference/calibration.py",
    "from ..scientific.serialization import require_schema, schema_string\n",
    "from ..scientific.results.immutable import freeze\nfrom ..scientific.serialization import require_schema, schema_string\n",
)
replace_once(
    "src/engcore/inference/calibration.py",
    '        object.__setattr__(self, "fixed", dict(fixed))\n'
    '        object.__setattr__(self, "initial_point", dict(initial))\n',
    '        object.__setattr__(self, "fixed", freeze(dict(fixed)))\n'
    '        object.__setattr__(self, "initial_point", freeze(dict(initial)))\n',
)
replace_once(
    "src/engcore/inference/calibration.py",
    '        if not str(self.termination_reason).strip():\n'
    '            raise CalibrationError("a calibration must say why it stopped")\n',
    '        residuals = tuple(float(value) for value in self.residuals)\n'
    '        if self.status is CalibrationStatus.CONVERGED and any(not math.isfinite(value) for value in residuals):\n'
    '            raise CalibrationError("a converged calibration cannot report non-finite residuals")\n'
    '        object.__setattr__(self, "residuals", residuals)\n'
    '        if not str(self.termination_reason).strip():\n'
    '            raise CalibrationError("a calibration must say why it stopped")\n',
)
replace_once(
    "src/engcore/inference/calibration.py",
    '            "evaluation_count": self.evaluation_count,\n'
    '            "provenance": self.provenance.to_dict(),\n'
    '        }\n\n\ndef calibrate(\n',
    '            "evaluation_count": self.evaluation_count,\n'
    '            "provenance": self.provenance.to_dict(),\n'
    '            "residuals": list(self.residuals),\n'
    '        }\n\n\ndef calibrate(\n',
)

# 8. A factory session whose identity cannot be weakly tracked is not a session
# whose freshness the registry can prove. Refuse instead of silently skipping.
replace_once(
    "src/engcore/scientific/solvers/registry.py",
    '        except TypeError:\n'
    '            # A ``__slots__`` solver without ``__weakref__``: nothing to track\n'
    '            # it by that would not keep it alive. The probe check still holds.\n'
    '            pass\n',
    '        except TypeError as exc:\n'
    '            label = f"{self._identity.solver_id}@{self._identity.version}"\n'
    '            raise TypeError(\n'
    '                f"the factory registered for {label} returned a solver session "\n'
    '                f"that cannot be weak-referenced; session freshness cannot be "\n'
    '                f"proven, so the registry refuses to issue it"\n'
    '            ) from exc\n',
)

TEST = r'''"""Regression coverage for trust-boundary findings 5-8."""

from __future__ import annotations

import math

import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import HybridUQResult, RouteClaim, RouteDecision
from engcore.scientific.solvers.protocol import SolverIdentity
from engcore.scientific.solvers.registry import SolverDefinition
from engcore.scientific.units.quantity import Quantity


def test_route_diagnostics_are_transitively_immutable() -> None:
    problem = S.affine()
    posterior = problem.local_posterior()
    diagnostics = posterior.diagnostics
    before = diagnostics.to_dict()
    digest = diagnostics.digest

    with pytest.raises(TypeError, match="immutable"):
        diagnostics.thresholds["nonlinearity_refuse"] = 999.0
    assert diagnostics.multistart
    with pytest.raises(TypeError, match="immutable"):
        diagnostics.multistart[0]["objective"] = 999.0

    assert diagnostics.to_dict() == before
    assert diagnostics.digest == digest


def test_hybrid_result_freezes_grid_summary_and_considered_recursively() -> None:
    result = HybridUQResult(
        decision=RouteDecision.REFUSED,
        approximation_class=None,
        claim=RouteClaim.REFUSED,
        parameter_names=(),
        coordinates="none",
        mean=None,
        covariance=None,
        local_posterior=None,
        grid_summary={"route": "test", "nested": {"points": [1, 2]}},
        considered=({"route": "local", "detail": "refused"},),
        identifiability=None,
    )
    before = result.to_dict()
    digest = result.digest

    with pytest.raises(TypeError, match="immutable"):
        result.grid_summary["route"] = "tampered"
    with pytest.raises(TypeError, match="immutable"):
        result.grid_summary["nested"]["points"] = [3]
    with pytest.raises(TypeError, match="immutable"):
        result.considered[0]["detail"] = "tampered"

    assert result.to_dict() == before
    assert result.digest == digest


def test_calibration_residuals_survive_serialization_and_spec_is_immutable() -> None:
    problem = S.affine()
    calibration = problem.calibrate()
    payload = calibration.to_dict()

    assert calibration.residuals
    assert len(calibration.residuals) == len(problem.observations.observations)
    assert all(math.isfinite(value) for value in calibration.residuals)
    assert payload["residuals"] == list(calibration.residuals)

    with pytest.raises(TypeError, match="immutable"):
        calibration.spec.fixed["tamper"] = Quantity(1.0, "dimensionless")
    name = next(iter(calibration.spec.initial_point))
    with pytest.raises(TypeError, match="immutable"):
        calibration.spec.initial_point[name] = Quantity(999.0, calibration.spec.initial_point[name].units)


def test_registry_refuses_a_session_whose_freshness_cannot_be_tracked() -> None:
    class NonWeakrefableSolver:
        __slots__ = ()

        @property
        def identity(self) -> SolverIdentity:
            return SolverIdentity("nonweak", "1")

    definition = SolverDefinition(NonWeakrefableSolver, NonWeakrefableSolver())
    with pytest.raises(TypeError, match="freshness cannot be proven"):
        definition.new_session()
'''

(ROOT / "tests/hybrid_uq/test_trust_repairs_5_8.py").write_text(TEST, encoding="utf-8")
print("trust repair 5-8 patch applied")
