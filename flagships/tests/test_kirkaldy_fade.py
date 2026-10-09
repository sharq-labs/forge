"""The Kirkaldy 2024 fade study's mechanics on synthetic archives: no download is needed.

The adversarial points: an RPT the cycle rows do not reach is skipped, never estimated; a wrong archive is refused; the
criteria are the pre-registered ones; model discrepancy is never quantified from a failed holdout.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile

import numpy as np
import pytest

from forge_flagships import kirkaldy_fade as kf


def _archive(path, expt, cells, *, truncate_last=False):
    """cells: {cell_id: (setpoint_C, k, ea)}; each cell: 4 RPTs, 40 cycles per set of 4 A h charge + 4 A h discharge."""
    with zipfile.ZipFile(path, "w") as z:
        root = f"Expt {expt} - Synthetic"
        for cell, (temp_c, k, ea) in cells.items():
            rows, perf = [], []
            q_dis = q_tot = 0.0
            for rpt in range(4):
                fade = float(kf.predict(k, ea, np.array([q_dis]), np.array([temp_c + 273.15]))[0])
                perf.append({"Ageing Sets": rpt, "Ageing Cycles": 40 * rpt, "Charge Throughput [A h]": q_tot,
                             "C/10 Capacity [mA h]": 5000.0 * (1.0 - fade), "Age set av. temperature [°C]": temp_c + 5 if rpt else ""})
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


def test_the_fit_recovers_a_known_law_and_the_holdout_judges_it_with_the_preregistered_criteria(tmp_path):
    truth = (6e-5, 40e3)
    _archive(tmp_path / "cal.zip", 5, {c: (t, *truth) for c, t in zip("ABCDEF", (10, 10, 25, 25, 40, 40))})
    _archive(tmp_path / "hold.zip", 4, {c: (t, *truth) for c, t in zip("ABC", (10, 25, 40))})
    cal, hold = kf.read_cells(str(tmp_path / "cal.zip")), kf.read_cells(str(tmp_path / "hold.zip"))
    f = kf.fit(cal)
    assert f["k_q_per_Ah_discharge"] == pytest.approx(truth[0], rel=1e-3)
    assert f["activation_energy_J_per_mol"] == pytest.approx(truth[1], rel=1e-3) and not f["activation_energy_at_bound"]
    prereg, _ = kf.load_preregistration()
    verdict = kf.judge(prereg, kf.holdout(hold, f["k_q_per_Ah_discharge"], f["activation_energy_J_per_mol"]))
    assert verdict["outcome"] == "MET" and verdict["C1"]["criterion"] == prereg["acceptance"]["C1"]
    wrong = kf.judge(prereg, kf.holdout(hold, 2 * truth[0], truth[1]))          # a doubled rate misses the holdout
    assert wrong["outcome"] == "NOT MET"


def test_an_rpt_the_cycle_rows_do_not_reach_is_skipped_with_its_reason_never_estimated(tmp_path):
    _archive(tmp_path / "cal.zip", 5, {"A": (25, 6e-5, 40e3)}, truncate_last=True)
    (cell,) = kf.read_cells(str(tmp_path / "cal.zip")).values()
    assert [c["rpt"] for c in cell["checkpoints"]] == [0, 1, 2]
    (skip,) = cell["skipped"]
    assert skip["rpt"] == 3 and "not estimated" in skip["reason"]
    assert cell["checkpoints"][1]["discharge_throughput_Ah"] == pytest.approx(160.0)          # discharge only, the charge-only step excluded
    assert cell["checkpoints"][1]["abs_current_throughput_Ah"] == pytest.approx(320.5)


def test_an_archive_that_is_not_the_preregistered_one_is_refused(tmp_path):
    prereg, _ = kf.load_preregistration()
    for role in ("calibration_set", "holdout_set"):
        (tmp_path / prereg["data"][role]["archive"]).write_bytes(b"not the archive")
    with pytest.raises(SystemExit, match="not the pre-registered archive"):
        kf.admit(str(tmp_path), prereg)


def test_the_preregistration_fixes_the_criteria_the_code_applies():
    prereg, sha = kf.load_preregistration()
    assert len(sha) == 64 and prereg["id"] == "big14-a-kirkaldy-fade"
    assert "<= 0.015" in prereg["acceptance"]["C1"] and "<= 0.010" in prereg["acceptance"]["C2"]
    assert kf.T_REF == 298.15 and kf.EA_BOUNDS == (0.0, 200e3)
    assert json.dumps(prereg["uncertainty_budget"]).count("never zero") >= 1
