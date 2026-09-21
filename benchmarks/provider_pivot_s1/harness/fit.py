"""P5: PyBOP fits the equivalent-circuit parameters, on calibration data only.

What is fitted, and why only two things
----------------------------------------
``R0`` and ``R1``. The Morris screen in ``sensitivity.py`` puts their mean
absolute elementary effects at 0.861 and 0.350 against 0.054, 0.051 and 0.019
for the initial charge state, the RC capacitance and the capacity scale -- an
order of magnitude apart. On a constant-current discharge the RC branch reaches
its steady value in a few time constants and ``C1`` stops moving the voltage, so
a fit asked to identify it would be handed a parameter the data does not carry.

That is the Sprint 3 recovery's own rule applied to a new fitter: it rejected a
second RC branch whose slower time constant scattered wider than its own median,
because a parameter that absorbs residuals is worse than no parameter. ``C1`` is
held at the recovery's own fitted polarization capacitance for the band.

How the fit is arranged, and what the spread is
-----------------------------------------------
One fit per calibration trajectory, then the **median** per operating block --
``group|corner|nominal_rate``, the recovery's own parameter unit. Per *band* was
tried first and reproduced that round's rate-dependence finding from the other
direction: ``R0``'s interquartile spread was 81 % across the warm band, which
pools 1 A, 2 A and 4 A discharges while a one-RC model's polarization is linear
in current.

Per-trajectory rather than pooled, because it buys the thing a pooled fit
cannot give: the spread of the per-trajectory estimates, which says whether the
parameter is a property of the cell or a property of the run.

The spread is reported as a dispersion and is **not** promoted to a parameter
uncertainty. It is not one: it has no probability model behind it, and
``FitEvidence.parameter_uncertainty`` stays ``None`` for exactly that reason.

    python benchmarks/provider_pivot_s1/harness/fit.py
"""

from __future__ import annotations

import os
import statistics as stats
import sys
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402

from engcore.providers import ExecutionOutcome  # noqa: E402
from engcore.providers import pybop_provider as bop  # noqa: E402

#: Held, not fitted. See the module docstring. Read from the recovery's own
#: frozen parameters so this round does not invent a third value for it.
def held_capacitance(band: str) -> float:
    blocks = common.preregistration()["frozen_parameters"]
    corner = "low_ambient" if band == "cold" else "room_ambient"
    values = [
        float(block["fitted"]["polarization_capacitance"])
        for key, block in blocks.items()
        if f"|{corner}|" in key
    ]
    if not values:
        raise SystemExit(f"no frozen polarization capacitance for band {band!r}")
    return stats.median(values)


#: Bounds. Wide enough that the fit is not the bound, narrow enough to stay
#: physical: a cell resistance below 10 mOhm or above 1 Ohm is not this cell.
BOUNDS = {
    "R0 [Ohm]": (0.01, 1.0),
    "R1 [Ohm]": (0.005, 0.5),
}
INITIAL = {"R0 [Ohm]": 0.15, "R1 [Ohm]": 0.06}


def fit_one(trajectory) -> dict[str, Any]:
    """One PyBOP fit against one calibration trajectory."""
    capacitance = held_capacitance(trajectory.band)
    dataset = bop.FitDataset(
        dataset_id=trajectory.trajectory_id,
        role=bop.DatasetRole.CALIBRATION,
        time_s=tuple(trajectory.time_s),
        current_a=tuple(trajectory.current_a),
        terminal_voltage_v=tuple(trajectory.voltage_v),
        provenance="NASA PCoE Li-ion battery aging archive, via the Sprint 3 "
        "recovery corpus; calibration split",
    )
    parameters = tuple(
        bop.FitParameter(
            name=name,
            lower=BOUNDS[name][0],
            upper=BOUNDS[name][1],
            initial=INITIAL[name],
        )
        for name in ("R0 [Ohm]", "R1 [Ohm]")
    )

    def model_factory():
        import pybamm

        return pybamm.equivalent_circuit.Thevenin()

    provider = bop.PyBOPProvider(
        dataset=dataset,
        parameters=parameters,
        model_factory=model_factory,
        parameter_values_factory=common.ecm_factory(
            trajectory.band,
            capacity_ah=trajectory.capacity_ah,
            ambient_k=trajectory.ambient_k,
            initial_temperature_k=trajectory.temperature_k[0],
            r0_ohm=INITIAL["R0 [Ohm]"],
            r1_ohm=INITIAL["R1 [Ohm]"],
            c1_farad=capacitance,
            initial_state_of_charge=common.ecm_initial_state_of_charge(trajectory),
        ),
        optimiser="scipy_minimize",
        objective="rmse",
    )
    outcome = provider.execute(
        bop.build_fit_request(
            dataset=dataset, parameters=parameters, qoi="terminal_voltage"
        )
    )
    row: dict[str, Any] = {
        "trajectory_id": trajectory.trajectory_id,
        "cell": trajectory.cell,
        "band": trajectory.band,
        "split": trajectory.split,
        "outcome": outcome.outcome.value,
        "detail": outcome.receipt.detail,
        "wall_seconds": outcome.receipt.wall_seconds,
        "held_capacitance_f": capacitance,
    }
    if outcome.outcome is ExecutionOutcome.OK:
        row["evidence"] = dict(outcome.evidence)
        row["identity"] = outcome.receipt.identity.to_dict()
    return row


def main() -> int:
    clock = time.perf_counter()
    trajectories = [
        common.windowed(t)
        for t in common.development_trajectories(("calibration",))
    ]
    print(
        f"{len(trajectories)} calibration trajectories, "
        f"{sum(t.sample_count for t in trajectories)} samples inside the "
        f"charge-state window both models claim"
    )

    rows = [fit_one(t) for t in trajectories]
    for row in rows:
        best = row.get("evidence", {}).get("best_values", {})
        print(
            f"  {row['trajectory_id']:16} {row['band']:5} {row['outcome']:14} "
            + " ".join(f"{k.split(' ')[0]}={v:.4f}" for k, v in sorted(best.items()))
        )

    bands: dict[str, dict[str, Any]] = {}
    units = {t.trajectory_id: (t.native_unit, t.band) for t in trajectories}
    for unit in sorted({u for u, _ in units.values()}):
        band = next(b for u, b in units.values() if u == unit)
        fitted = [
            r
            for r in rows
            if units[r["trajectory_id"]][0] == unit and r["outcome"] == "ok"
        ]
        if not fitted:
            bands[unit] = {"fits": 0, "refused": "no calibration fit succeeded"}
            continue
        per_parameter: dict[str, Any] = {}
        for name in ("R0 [Ohm]", "R1 [Ohm]"):
            values = sorted(r["evidence"]["best_values"][name] for r in fitted)
            median = stats.median(values)
            per_parameter[name] = {
                "median": median,
                "minimum": values[0],
                "maximum": values[-1],
                "interquartile_spread": (
                    values[int(0.75 * (len(values) - 1))]
                    - values[int(0.25 * (len(values) - 1))]
                ),
                "relative_interquartile_spread": (
                    (
                        values[int(0.75 * (len(values) - 1))]
                        - values[int(0.25 * (len(values) - 1))]
                    )
                    / median
                    if median
                    else None
                ),
                "n": len(values),
            }
        at_bound = sorted(
            {
                name
                for r in fitted
                for name in r["evidence"]["diagnostics"]["parameters_at_bound"]
            }
        )
        authority = common.derived_authority(
            band,
            unit=unit,
            r0_ohm=per_parameter["R0 [Ohm]"]["median"],
            r1_ohm=per_parameter["R1 [Ohm]"]["median"],
            c1_farad=held_capacitance(band),
            note=(
                f"median of {len(fitted)} per-trajectory PyBOP fits on the "
                f"calibration split, operating block {unit!r} (band {band!r}). "
                f"C1 held at the Sprint 3 recovery's own fitted polarization "
                f"capacitance because the Morris screen puts its influence an "
                f"order of magnitude below R0 and R1"
            ),
        )
        bands[unit] = {
            "band": band,
            "fits": len(fitted),
            "parameters": per_parameter,
            "held_capacitance_f": held_capacitance(band),
            "parameters_at_bound": at_bound,
            "authority": authority.to_dict(),
            "authority_digest": authority.digest(),
            "parent_authority_digest": authority.parent_authority_digest,
        }
        spread = per_parameter["R0 [Ohm]"]["relative_interquartile_spread"]
        print(
            f"{unit:26} n={len(fitted):3}  "
            f"R0={per_parameter['R0 [Ohm]']['median']:.4f} "
            f"(IQR {spread:.1%})  "
            f"R1={per_parameter['R1 [Ohm]']['median']:.4f}  "
            f"digest {authority.digest()[:12]}"
        )
        if at_bound:
            print(f"      parameters that rested on a bound somewhere: {at_bound}")

    record = {
        "schema": "provider_pivot_s1_fit/1",
        "split_fitted": "calibration",
        "what_was_not_seen": [
            "validation",
            "observed_holdout",
            "locked_holdout",
        ],
        "fitted_parameters": ["R0 [Ohm]", "R1 [Ohm]"],
        "held_parameters": {
            "C1 [F]": "the Sprint 3 recovery's fitted polarization capacitance "
            "for the band; held because the Morris screen ranks it an order of "
            "magnitude below R0 and R1"
        },
        "sensitivity_evidence": "SENSITIVITY.json",
        "sensitivity_is_validation_evidence": False,
        "bounds": {k: list(v) for k, v in BOUNDS.items()},
        "initial_values": dict(INITIAL),
        "priors": None,
        "priors_note": (
            "no prior was declared, so none was used. A uniform prior over the "
            "bounds would be a choice this round did not make"
        ),
        "parameter_uncertainty": None,
        "parameter_uncertainty_note": (
            "the per-trajectory spread below is a DISPERSION of point "
            "estimates, not a calibrated parameter uncertainty. Promoting it "
            "to one would invent a probability model nothing here supports"
        ),
        "parameter_unit": "group|corner|nominal_rate -- the Sprint 3 recovery's own operating block",
        "blocks": bands,
        "per_trajectory": rows,
        "wall_seconds": time.perf_counter() - clock,
    }
    path = common.write_evidence("FIT.json", record)
    print(f"wrote {path} in {record['wall_seconds']:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
