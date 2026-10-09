"""The Kirkaldy 2024 fade study's mechanics on synthetic archives: no download is needed.

The adversarial points: an RPT the cycle rows do not reach, or whose throughput or capacity is missing, is skipped, never
estimated or zeroed; a wrong archive is refused; a shared test channel is refused; the criteria are the pre-registered ones and
need every registered temperature; a parameter pinned at a bound gets no uncertainty; model discrepancy is never quantified from
a failed holdout; the study's law is the domain model's law.
"""

from __future__ import annotations

import csv
import io
import zipfile

import numpy as np
import pytest

from forge_flagships import kirkaldy_fade as kf

PREREGISTRATION_SHA256 = "da6ac0da6c1ee88285a85f575f7ab0046b1d37563ac68d9658c3d10b19ca1c19"   # the bytes pushed in dd53eec7


def _archive(path, expt, cells, *, truncate_last=False, blank_c10_rpt=None, blank_throughput_rpt=None, no_bol=False):
    """cells: {cell_id: (setpoint_C, k, ea)}; each cell: 4 RPTs, 40 cycles per set of 4 A h charge + 4 A h discharge."""
    with zipfile.ZipFile(path, "w") as z:
        root = f"Expt {expt} - Synthetic"
        for cell, (temp_c, k, ea) in cells.items():
            rows, perf = [], []
            q_dis = q_tot = 0.0
            for rpt in range(4):
                fade = float(kf.predict(k, ea, np.array([q_dis]), np.array([temp_c + 273.15]))[0])
                perf.append({"Ageing Sets": rpt, "Ageing Cycles": 40 * rpt,
                             "Charge Throughput [A h]": "" if rpt == blank_throughput_rpt else q_tot,
                             "C/10 Capacity [mA h]": "" if rpt == blank_c10_rpt or (no_bol and rpt == 0) else 5000.0 * (1.0 - fade),
                             "Age set av. temperature [°C]": temp_c + 5 if rpt else ""})
                if rpt == 3:
                    break
                for n in range(40):
                    if truncate_last and rpt == 2 and n >= 20:
                        q_dis += 4.0
                        q_tot += 8.0
                        continue                                   # the cycle file loses the rest of the last set
                    rows.append({"Cycle": n, "Discharge Capacity [A h]": 4.0, "Charge Capacity [A h]": 4.0})
                    q_dis += 4.0
                    q_tot += 8.0
                rows.append({"Cycle": "", "Discharge Capacity [A h]": "", "Charge Capacity [A h]": 0.5})   # a charge-only step
                q_tot += 0.5
            for name, data, fields in (
                (f"{root}/Summary Data/Performance Summary/Expt {expt} - cell {cell} ({temp_c}degC) - Processed Data.csv", perf, list(perf[0])),
                (f"{root}/Summary Data/Ageing Sets Summary/Summary per Cycle/expt {expt} - cell {cell} - cycle_data.csv", rows, list(rows[0])),
            ):
                buf = io.StringIO()
                w = csv.DictWriter(buf, fieldnames=fields)
                w.writeheader()
                w.writerows(data)
                z.writestr(name, buf.getvalue())


def _cells(tmp_path, name, expt, spec, **kw):
    _archive(tmp_path / name, expt, spec, **kw)
    return kf.read_cells(str(tmp_path / name))


def test_the_fit_recovers_a_known_law_and_the_holdout_judges_it_with_the_preregistered_criteria(tmp_path):
    truth = (6e-5, 40e3)
    cal = _cells(tmp_path, "cal.zip", 5, {c: (t, *truth) for c, t in zip("ABCDEF", (10, 10, 25, 25, 40, 40))})
    hold = _cells(tmp_path, "hold.zip", 4, {c: (t, *truth) for c, t in zip("ABC", (10, 25, 40))})
    f = kf.fit(cal)
    assert f["k_q_per_Ah_discharge"] == pytest.approx(truth[0], rel=1e-3)
    assert f["activation_energy_J_per_mol"] == pytest.approx(truth[1], rel=1e-3) and not f["activation_energy_at_bound"]
    prereg, _ = kf.load_preregistration()
    h = kf.holdout(hold, f["k_q_per_Ah_discharge"], f["activation_energy_J_per_mol"])
    assert all(r["rpt"] != 0 for r in h["rows"]) and not h["reference_rpt_included"]        # the normalisation point is not a prediction
    verdict = kf.judge(prereg, h)
    assert verdict["outcome"] == "MET" and verdict["C1"]["criterion"] == prereg["acceptance"]["C1"]
    assert kf.model_discrepancy(verdict, h)["status"].startswith("QUANTIFIED")
    wrong = kf.judge(prereg, kf.holdout(hold, 2 * truth[0], truth[1]))          # a doubled rate misses the holdout
    assert wrong["outcome"] == "NOT MET"
    assert kf.model_discrepancy(wrong, h) == {"status": "NOT QUANTIFIED (unknown, not zero)", "reason": "the pre-registered holdout criteria were not met"}


def test_c2_needs_every_registered_temperature_a_missing_one_is_not_met(tmp_path):
    truth = (6e-5, 40e3)
    hold = _cells(tmp_path, "hold.zip", 4, {c: (t, *truth) for c, t in zip("AB", (10, 40))})       # no 25 degC cell
    prereg, _ = kf.load_preregistration()
    verdict = kf.judge(prereg, kf.holdout(hold, *truth))
    assert verdict["C1"]["met"] and verdict["C2"]["missing_temperatures"] == ["25C"]
    assert verdict["C2"]["met_per_temperature"]["25C"] is False and verdict["outcome"] == "NOT MET"


def test_a_parameter_pinned_at_a_bound_gets_no_uncertainty_and_the_other_is_labelled_conditional(tmp_path):
    # cold cells fade faster, as in the real data: the unconstrained optimum is a negative activation energy
    cal = _cells(tmp_path, "cal.zip", 5, {"A": (10, 9e-5, 0.0), "B": (25, 6e-5, 0.0), "C": (25, 6e-5, 0.0), "D": (40, 6e-5, 0.0)})
    assert kf.fit(cal)["activation_energy_at_bound"]
    loo = kf.leave_one_cell_out(cal)
    # leaving out the one cold cell frees the activation energy in that refit; one pinned refit is enough to withhold a spread
    assert loo["activation_energy"] == {"status": "NOT ESTABLISHED (constraint-active at a bound in 3/4 refits)"}
    assert "std" not in loo["activation_energy"] and loo["k_q"]["conditional_on"] == "activation energy at a bound in some refits"


def test_an_rpt_the_cycle_rows_do_not_reach_is_skipped_with_its_reason_never_estimated(tmp_path):
    (cell,) = _cells(tmp_path, "cal.zip", 5, {"A": (25, 6e-5, 40e3)}, truncate_last=True).values()
    assert [c["rpt"] for c in cell["checkpoints"]] == [0, 1, 2]
    (skip,) = cell["skipped"]
    assert skip["rpt"] == 3 and "not estimated" in skip["reason"]
    assert cell["checkpoints"][1]["discharge_throughput_Ah"] == pytest.approx(160.0)          # discharge only, the charge-only step excluded
    assert cell["checkpoints"][1]["abs_current_throughput_Ah"] == pytest.approx(320.5)
    assert cell["cycle_rows"]["charge_only_unnumbered"] == 3


def test_a_missing_throughput_or_capacity_is_skipped_never_read_as_zero(tmp_path):
    (cell,) = _cells(tmp_path, "t.zip", 5, {"A": (25, 6e-5, 40e3)}, blank_throughput_rpt=2).values()
    assert [c["rpt"] for c in cell["checkpoints"]] == [0, 1, 3] and "not taken as zero" in cell["skipped"][0]["reason"]
    (cell,) = _cells(tmp_path, "c.zip", 5, {"A": (25, 6e-5, 40e3)}, blank_c10_rpt=1).values()
    assert [c["rpt"] for c in cell["checkpoints"]] == [0, 2, 3] and "no C/10 capacity" in cell["skipped"][0]["reason"]
    with pytest.raises(SystemExit, match="no beginning-of-life capacity"):
        _cells(tmp_path, "b.zip", 5, {"A": (25, 6e-5, 40e3)}, no_bol=True)


def test_a_shared_test_channel_between_calibration_and_holdout_is_refused(tmp_path):
    cal = _cells(tmp_path, "cal.zip", 5, {"A": (25, 6e-5, 40e3)})
    hold = _cells(tmp_path, "hold.zip", 4, {"A": (25, 6e-5, 40e3)})
    ok = kf.independent(cal, hold, {("expt 5", "A"): "Rig1/CC4", ("expt 4", "A"): "Rig1/CC1"})
    assert ok["shared_channels"] == []
    with pytest.raises(SystemExit, match="share test channels"):
        kf.independent(cal, hold, {("expt 5", "A"): "Rig1/CC4", ("expt 4", "A"): "Rig1/CC4"})
    with pytest.raises(SystemExit, match="not in the metadata"):
        kf.independent(cal, hold, {("expt 5", "A"): "Rig1/CC4"})


def test_an_archive_that_is_not_the_preregistered_one_is_refused(tmp_path):
    prereg, _ = kf.load_preregistration()
    for role in ("calibration_set", "holdout_set"):
        (tmp_path / prereg["data"][role]["archive"]).write_bytes(b"not the archive")
    with pytest.raises(SystemExit, match="not the pre-registered archive"):
        kf.admit(str(tmp_path), prereg)


def test_the_preregistration_is_the_pushed_bytes_and_fixes_the_criteria_the_code_applies():
    prereg, sha = kf.load_preregistration()
    assert sha == PREREGISTRATION_SHA256 and prereg["id"] == "big14-a-kirkaldy-fade"
    assert f"<= {kf.C1_RMSE_MAX}" in prereg["acceptance"]["C1"] and f"<= {kf.C2_BIAS_MAX:.3f}" in prereg["acceptance"]["C2"]
    assert kf.T_REF == 298.15 and kf.EA_BOUNDS == (0.0, 200e3)


def test_the_study_law_is_the_domain_models_law():
    from engcore.domains.battery.throughput_fade import ThroughputArrheniusFade
    from engcore.scientific.units.quantity import Quantity
    for k, ea, q, t in ((6e-5, 40e3, 300.0, 283.15), (2e-4, 30e3, 1200.0, 313.15), (5.7e-5, 0.0, 4000.0, 298.15)):
        model = ThroughputArrheniusFade(k_per_ampere_hour=Quantity(k, "1/(A*h)"), activation_energy=Quantity(ea, "J/mol"),
                                        reference_temperature=Quantity(kf.T_REF, "K"))
        out = model.advance({"charge_throughput": Quantity(q, "A*h"), "mean_cell_temperature": Quantity(t, "K")},
                            {"capacity_fade": Quantity(0.0, "dimensionless")}, Quantity(1.0, "s"))
        assert out["capacity_fade"].magnitude_in("dimensionless") == pytest.approx(float(kf.predict(k, ea, np.array([q]), np.array([t]))[0]), rel=1e-12)
