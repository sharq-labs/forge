"""P6: which parameters move the voltage, before anything is fitted.

Morris elementary effects over the equivalent-circuit parameters, evaluated by
the PyBaMM provider, analysed by SALib. Forge chooses the parameters and their
ranges, evaluates the design, and decides what the answer is for; SALib does the
sampling and the estimator and nothing else.

Why this runs before the fit
-----------------------------
The Sprint 3 recovery rejected a second RC branch because its slower time
constant scattered wider than its own median -- a free parameter absorbing
residuals rather than a second physical process. The general form of that
failure is fitting more parameters than the data can identify. A sensitivity
ranking is the cheap way to see which parameters the response actually carries,
*before* a fit is asked to identify them.

And the answer it gives is evidence, not validation. A parameter can dominate
the response of a model that is wrong about everything.

    python benchmarks/provider_pivot_s1/harness/sensitivity.py
"""

from __future__ import annotations

import math
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

from engcore.providers import ExecutionOutcome  # noqa: E402
from engcore.providers import pybamm_provider as pp  # noqa: E402
from engcore.providers import salib_provider as sal  # noqa: E402

#: The five parameters an equivalent-circuit prediction of terminal voltage can
#: depend on here, and the range each is varied over. Ranges are declared, not
#: discovered: the two resistances span the measured branch-difference spread
#: the recovery reported (0.133 to 0.499 ohm across charge state and band), the
#: time constant spans the relaxation it measured, and the two state parameters
#: span their own authorities' reported uncertainty.
#:
#: The charge-state range stops at 0.999 rather than 1.000 because the ECM's own
#: state interval is open: at exactly 1.0 the model's ``Maximum SoC`` event is
#: non-positive at the initial condition and the adapter declines the point as
#: MODEL_NOT_APPLICABLE. A screening design that spent a sixth of its points on
#: a boundary the model refuses would be measuring the refusal, not the
#: sensitivity -- and it did: the first run of this module reported
#: MISSING_EVIDENCE on 12 of 72 points, every one of them at 1.0. The range is
#: narrowed to the model's applicable interior and the reason is written here
#: rather than the refusal being repaired with a substituted value.
PARAMETERS = (
    sal.SensitivityParameter("R0 [Ohm]", 0.05, 0.50),
    sal.SensitivityParameter("R1 [Ohm]", 0.01, 0.25),
    sal.SensitivityParameter("C1 [F]", 200.0, 5000.0),
    sal.SensitivityParameter("initial_state_of_charge", 0.90, 0.999),
    sal.SensitivityParameter("capacity_scale", 0.95, 1.05),
)

#: Morris trajectories. Small on purpose: Morris is a screening method and the
#: question here is which parameters matter at all, not how much.
MORRIS_TRAJECTORIES = 12

#: The scenario. One calibration trajectory, named, because a sensitivity index
#: without its scenario is not interpretable.
SCENARIO_SPLIT = "calibration"


def pick_scenario():
    """The longest warm calibration trajectory, which is the most informative.

    Chosen by a declared rule rather than by eye, and from calibration only.
    """
    candidates = [
        t
        for t in common.development_trajectories((SCENARIO_SPLIT,))
        if t.band == "warm" and t.sample_count >= 100
    ]
    if not candidates:
        raise SystemExit("no warm calibration trajectory long enough to screen on")
    return max(candidates, key=lambda t: t.duration_s)


def rmse_evaluator(trajectory):
    """Voltage RMSE of one PyBaMM ECM run against the measured trajectory.

    Returns ``None`` when the provider did not deliver. ``None`` is the honest
    answer and SALib's caller refuses the whole study rather than substituting
    a value; see :class:`~engcore.providers.salib_provider.SALibProvider`.
    """

    from engcore.data import BulkDataResolver, InMemoryBulkStore

    def evaluate(point: dict[str, float]) -> float | None:
        capacity = trajectory.capacity_ah * float(point["capacity_scale"])
        store = InMemoryBulkStore()
        authority = common.derived_authority(
            trajectory.band,
            r0_ohm=point["R0 [Ohm]"],
            r1_ohm=point["R1 [Ohm]"],
            c1_farad=point["C1 [F]"],
            note="one Morris design point; not a fitted authority",
        )
        protocol = pp.CurrentProtocol(
            duration_s=trajectory.duration_s,
            times_s=tuple(trajectory.time_s),
            currents_a=tuple(trajectory.current_a),
        )
        cell = pp.CellUnderTest(
            cell_id=trajectory.cell,
            chemistry=common.CELL_CHEMISTRY,
            nominal_capacity_ah=capacity,
            ambient_temperature_k=trajectory.ambient_k,
        )
        provider = pp.PyBaMMProvider(
            authority=authority,
            cell=cell,
            protocol=protocol,
            parameter_values_factory=common.ecm_factory(
                trajectory.band,
                capacity_ah=capacity,
                ambient_k=trajectory.ambient_k,
                initial_temperature_k=trajectory.temperature_k[0],
                r0_ohm=point["R0 [Ohm]"],
                r1_ohm=point["R1 [Ohm]"],
                c1_farad=point["C1 [F]"],
            ),
            store=store,
        )
        request = pp.build_request(
            model_key="thevenin_1rc",
            authority=authority,
            cell=cell,
            protocol=protocol,
            qois=("terminal_voltage", "time"),
            initial_state_of_charge=float(point["initial_state_of_charge"]),
        )
        outcome = provider.execute(request)
        if outcome.outcome is not ExecutionOutcome.OK or outcome.result is None:
            return None
        # One execution per design point. The scalar values on the result are
        # end-of-protocol; the series this RMSE needs travels as digested bulk
        # references, resolved through the store the provider wrote them to.
        resolver = BulkDataResolver(store)
        series = {
            reference.name.rsplit(":", 1)[1]: resolver.resolve(reference)
            for reference in outcome.result.data_references
        }
        if "time" not in series or "terminal_voltage" not in series:
            return None
        predicted = common.interpolate(
            series["time"], series["terminal_voltage"], trajectory.time_s
        )
        residuals = [
            p - m for p, m in zip(predicted, trajectory.voltage_v) if p is not None
        ]
        if not residuals:
            return None
        return math.sqrt(sum(r * r for r in residuals) / len(residuals))

    return evaluate


def main() -> int:
    trajectory = pick_scenario()
    scenario_id = f"{trajectory.trajectory_id}:{trajectory.band}"
    print(
        f"scenario {scenario_id}  n={trajectory.sample_count}  "
        f"duration={trajectory.duration_s:.0f}s  split={trajectory.split}"
    )

    provider = sal.SALibProvider(
        method="morris",
        parameters=PARAMETERS,
        qoi="terminal_voltage_rmse",
        scenario_id=scenario_id,
        evaluator=rmse_evaluator(trajectory),
        samples=MORRIS_TRAJECTORIES,
    )
    request = sal.build_sensitivity_request(
        method="morris",
        parameters=PARAMETERS,
        qoi="terminal_voltage_rmse",
        scenario_id=scenario_id,
        samples=MORRIS_TRAJECTORIES,
    )
    outcome = provider.execute(request)
    print(f"outcome {outcome.outcome.value}: {outcome.receipt.detail}")
    if outcome.outcome is not ExecutionOutcome.OK:
        common.write_evidence(
            "SENSITIVITY.json",
            {
                "schema": "provider_pivot_s1_sensitivity/1",
                "outcome": outcome.outcome.value,
                "detail": outcome.receipt.detail,
                "scenario_id": scenario_id,
                "is_validation_evidence": False,
            },
        )
        return 1

    evidence: dict[str, Any] = dict(outcome.evidence)
    record = {
        "schema": "provider_pivot_s1_sensitivity/1",
        "outcome": outcome.outcome.value,
        "scenario": {
            "trajectory_id": trajectory.trajectory_id,
            "cell": trajectory.cell,
            "split": trajectory.split,
            "band": trajectory.band,
            "samples": trajectory.sample_count,
            "duration_s": trajectory.duration_s,
            "ambient_k": trajectory.ambient_k,
        },
        "provider_identity": outcome.receipt.identity.to_dict(),
        "wall_seconds": outcome.receipt.wall_seconds,
        "evidence": evidence,
        "what_this_decides": (
            "which parameters are worth fitting. It decides nothing about "
            "whether the model agrees with the world"
        ),
    }
    common.write_evidence("SENSITIVITY.json", record)
    primary = evidence["primary_index"]
    print(f"ranking by {primary} ({evidence['primary_index_meaning']}):")
    for name in evidence["ranking"]:
        print(f"  {name:32} {evidence['indices'][name].get(primary):12.5g}")
    print(f"is_validation_evidence = {evidence['is_validation_evidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
