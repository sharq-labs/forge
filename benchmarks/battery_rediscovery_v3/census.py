"""Real-data asset census for battery_rediscovery_v3 (evaluator side; written before any truth exists).

    python -m benchmarks.battery_rediscovery_v3.census      # writes EvaluatorVault/CENSUS.json

Every battery dataset available in the repository or in approved local research data (``D:/forge-data``) is listed, per
cell (or file) and condition, with: identity and hash, temperature, protocol and current conditions, measurement
channels, uncertainty information, provenance, prior FORGE use, and whether an outcome for it is already known in the
current evaluator context.  Nothing here fits a model or compares a voltage with one; the computed fields are protocol
facts (ambient label, load level, charge termination current, sampling interval, recorded temperature range).

Classes (a unit may carry several; ``primary_class`` is the one that decides its use):

* ``UNUSED_BY_MIND``            never in a v0, v1, v2 or repsem pack.
* ``USED_IN_V0`` / ``USED_IN_V1`` / ``USED_IN_V2``   in that benchmark's pack.
* ``USED_ONLY_FOR_DEVELOPMENT`` read during Gen1 development (repsem fixtures are synthetic: none of these units).
* ``HISTORICAL_TRUTH_EXPOSED``  an outcome of a 1RC/voltage-model question on this unit is known in the evaluator context
                                (repository records or the evaluator's project memory).
* ``ELIGIBLE_PRIMARY_V3``       UNUSED_BY_MIND, not HISTORICAL_TRUTH_EXPOSED, and passes the structural screen.
* ``ELIGIBLE_SECONDARY_ONLY``   usable data, but used by the Mind or truth-exposed: at most a labelled bridge set.
* ``INELIGIBLE``                fails the structural screen (reason recorded).

The structural screen (cell level) is fixed in ``SCREEN`` before any pack is built; it uses protocol metadata only.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

import numpy as np

from benchmarks.battery_rediscovery_v2.candidate.common import write_json

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VAULT = HERE / "EvaluatorVault"
DATA = pathlib.Path("D:/forge-data")
NASA_DIR = DATA / "nasa_pcoe_battery"

SCREEN = {
    "channels": "time, terminal voltage, current and cell temperature recorded for every sample; finite; time strictly "
                "increasing",
    "units": "known from the publisher's file header or README",
    "protocol_roles": "the run kind is one the Gen1 families can pose (constant-current discharge then rest, or rest-pulse-"
                      "rest) and the controlled current is a constant protocol level within each loaded segment",
    "initial_state": "the protocol's declared initial state is attained: the preceding charge ends in CV at the protocol "
                     "termination current plus the declared 10 mA current band (NASA: 20 mA + 10 mA; Chen 2020: C/100 = "
                     "50 mA + 10 mA), or the run starts from a declared rest whose state is fixed by the run's own protocol "
                     "(Kirkaldy GITT: charge state 1 at the end of the pre-GITT rest by convention)",
    "sample_density": "loaded segments sampled at <= 30 s and rests at <= 30 s",
    "uncertainty": "a voltage accuracy statement is used only if the publisher states one; otherwise UNKNOWN (never "
                   "invented, never zero)",
    "model_family": "a declared Thevenin 1RC family exists for the run kind: measured OCV (rest-ended GITT) or fitted "
                    "piecewise-linear OCV (constant-current discharges)",
    "separable_windows": "calibration and held-out trajectories are disjoint in time",
    "identity": "one physical cell per file with a published identity",
    "provenance": "publisher checksum or pinned sha256 for every raw file",
}

# ---- prior use, from repository paths (git grep at the v3 base) and the evaluator's project memory -------------------
PRIOR = {
    "nasa": {
        ("B0005", "B0006", "B0007", "B0018"): ({"USED_IN_V0", "USED_IN_V1", "HISTORICAL_TRUTH_EXPOSED"},
            "battery_1rc_closure split (v0/v1 P1); closure results (calibration NOT_IDENTIFIABLE, cross-cell FAIL) and "
            "Sprint 3 voltage results are in the evaluator context"),
        ("B0025", "B0026", "B0027", "B0028"): (set(), "no FORGE 1RC study"),
        ("B0029", "B0030", "B0031", "B0032"): (set(), "no repository record names these cells; project memory says Sprint 3 "
                                                      "splits touched every cell but B0041 (non-Mind; no outcome for these "
                                                      "cells is known in the evaluator context)"),
        ("B0033", "B0034", "B0036"): ({"HISTORICAL_TRUTH_EXPOSED"}, "Sprint 3 consumed every 20-30 C cell (non-Mind); B0036's "
                                      "temperature-channel defect and the 24 C 4 A capacity-basis break are known"),
        ("B0038", "B0039", "B0040"): ({"USED_IN_V2", "HISTORICAL_TRUTH_EXPOSED"}, "v2 Q1 (44 C runs); v2 truth is known; "
                                      "24 C runs consumed by Sprint 3"),
        ("B0041", "B0042", "B0043", "B0044"): ({"HISTORICAL_TRUTH_EXPOSED"}, "Sprint 3 holdout B0044 failed at 99.7 mV and "
                                               "B0041 failed at +128 mV bias in the recovery (project memory)"),
        ("B0045", "B0046", "B0047", "B0048", "B0049", "B0050", "B0051", "B0052", "B0053", "B0054", "B0055", "B0056"):
            (set(), "no repository record; project memory says Sprint 3 splits touched every cell but B0041 (non-Mind; no "
                    "outcome for these cells is known in the evaluator context)"),
    },
}
NASA_GROUP = {"1. BatteryAgingARC-FY08Q4": ("B0005", "B0006", "B0007", "B0018"),
              "2. BatteryAgingARC_25_26_27_28_P1": (),
              "3. BatteryAgingARC_25-44": ("B0025", "B0026", "B0027", "B0028", "B0029", "B0030", "B0031", "B0032", "B0033",
                                           "B0034", "B0036", "B0038", "B0039", "B0040", "B0041", "B0042", "B0043", "B0044"),
              "4. BatteryAgingARC_45_46_47_48": ("B0045", "B0046", "B0047", "B0048"),
              "5. BatteryAgingARC_49_50_51_52": ("B0049", "B0050", "B0051", "B0052"),
              "6. BatteryAgingARC_53_54_55_56": ("B0053", "B0054", "B0055", "B0056")}
NASA_CUTOFF_V = {"B0005": 2.7, "B0006": 2.5, "B0007": 2.2, "B0018": 2.5, "B0025": 2.0, "B0026": 2.2, "B0027": 2.5,
                 "B0028": 2.7, "B0029": 2.0, "B0030": 2.2, "B0031": 2.5, "B0032": 2.7, "B0033": 2.0, "B0034": 2.2,
                 "B0036": 2.7, "B0038": 2.2, "B0039": 2.5, "B0040": 2.7, "B0041": 2.0, "B0042": 2.2, "B0043": 2.5,
                 "B0044": 2.7, "B0045": 2.0, "B0046": 2.2, "B0047": 2.5, "B0048": 2.7, "B0049": 2.0, "B0050": 2.2,
                 "B0051": 2.5, "B0052": 2.7, "B0053": 2.0, "B0054": 2.2, "B0055": 2.5, "B0056": 2.7}
NASA_ARCHIVE_SHA256 = "82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e"
NASA_TERMINATION_A = 0.020
CURRENT_BAND_A = 0.010
NASA_LEVELS_A = {"B0038": (1.0, 2.0, 4.0), "B0039": (1.0, 2.0, 4.0), "B0040": (1.0, 2.0, 4.0), "B0041": (1.0, 4.0),
                 "B0042": (1.0, 4.0), "B0043": (1.0, 4.0), "B0044": (1.0, 4.0)}  # README: multiple fixed load levels
LEVEL_TOLERANCE = 0.05
MIN_LEVEL_FRACTION = 0.90


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _prior(cell: str) -> tuple[set[str], str]:
    for cells, (classes, note) in PRIOR["nasa"].items():
        if cell in cells:
            return set(classes), note
    raise KeyError(cell)


def nasa_rows() -> list[dict[str, Any]]:
    import scipy.io as sio  # noqa: PLC0415

    inventory = json.loads((NASA_DIR / "inventory.json").read_bytes())
    pinned = {f["extracted_to"]: f["sha256"] for inner in inventory["inner"] for f in inner["files"]}
    rows = []
    for group, cells in NASA_GROUP.items():
        for cell in cells:
            rel = f"extracted/{group}/{cell}.mat"
            path = NASA_DIR / rel
            sha = _sha(path)
            m = sio.loadmat(path, squeeze_me=True, struct_as_record=False)[cell]
            cycles = list(m.cycle)
            dis = [c for c in cycles if c.type == "discharge"]
            amb = sorted({int(c.ambient_temperature) for c in dis})
            levels, term, dts, tmin, tmax, levels_ok = [], [], [], [], [], 0
            for k, c in enumerate(cycles):
                if c.type != "discharge":
                    continue
                i = -np.asarray(c.data.Current_measured, float)
                t = np.asarray(c.data.Time, float)
                temp = np.asarray(c.data.Temperature_measured, float)
                lv = float(np.median(i[i > 0.3])) if np.any(i > 0.3) else 0.0
                levels.append(lv)
                if t.size > 1:
                    dts.append(float(np.median(np.diff(t))))
                if temp.size:
                    tmin.append(float(temp.min()))
                    tmax.append(float(temp.max()))
                prev = [p for p in cycles[:k] if p.type == "charge"]
                if prev:
                    ci = np.asarray(prev[-1].data.Current_measured, float)
                    if ci.size and np.isfinite(ci[-1]):
                        term.append(abs(float(ci[-1])))
            nominal = float(np.median(levels)) if levels else 0.0
            declared = NASA_LEVELS_A.get(cell, (min((1.0, 2.0, 4.0), key=lambda x: abs(x - nominal)),))
            nominal_level = declared[0] if len(declared) == 1 else list(declared)
            levels_ok = sum(any(abs(lv - d) <= LEVEL_TOLERANCE * d for d in declared) for lv in levels)
            frac_level = levels_ok / len(levels) if levels else 0.0
            term_med = float(np.median(term)) if term else None
            classes, note = _prior(cell)
            reasons = []
            if cell in ("B0025", "B0026", "B0027", "B0028"):
                reasons.append("protocol_roles: 0.05 Hz square-wave load sampled at ~10 s cannot be reconstructed between "
                               "samples")
            if term_med is None or term_med > NASA_TERMINATION_A + CURRENT_BAND_A:
                reasons.append(f"initial_state: median preceding-charge end current {None if term_med is None else round(term_med * 1e3, 1)} "
                               f"mA > {round((NASA_TERMINATION_A + CURRENT_BAND_A) * 1e3)} mA: the protocol's full charge is "
                               "not attained")
            if frac_level < MIN_LEVEL_FRACTION:
                reasons.append(f"protocol_roles: only {frac_level:.0%} of discharges run at the declared load level "
                               f"(< {MIN_LEVEL_FRACTION:.0%}; README: anomalous low-capacity runs)")
            if len(amb) > 1:
                reasons.append(f"protocol_roles: mixed ambient labels {amb} within one cell")
            if "USED_IN_V0" not in classes and "USED_IN_V1" not in classes and "USED_IN_V2" not in classes:
                classes.add("UNUSED_BY_MIND")
            if reasons:
                primary = "INELIGIBLE"
            elif classes & {"USED_IN_V0", "USED_IN_V1", "USED_IN_V2", "HISTORICAL_TRUTH_EXPOSED"}:
                primary = "ELIGIBLE_SECONDARY_ONLY"
            else:
                primary = "ELIGIBLE_PRIMARY_V3"
            rows.append({
                "dataset": "NASA PCoE Li-ion battery aging (18650, 2 Ah rated)", "unit": cell, "condition": group,
                "identity": {"file": rel, "sha256": sha, "pinned_sha256": pinned.get(rel),
                             "archive_sha256": NASA_ARCHIVE_SHA256},
                "temperature": {"ambient_labels_C": amb, "recorded_cell_C_range": [min(tmin), max(tmax)] if tmin else None},
                "protocol": {"discharges": len(dis), "load_level_A_median": nominal, "nominal_level_A": nominal_level,
                             "fraction_at_level": frac_level, "cutoff_V": NASA_CUTOFF_V.get(cell),
                             "charge_termination_A_median": term_med, "protocol_termination_A": NASA_TERMINATION_A,
                             "sampling_s_median": float(np.median(dts)) if dts else None},
                "channels": ["Time", "Voltage_measured", "Current_measured", "Temperature_measured", "Capacity (to 2.7 V)"],
                "uncertainty": "UNKNOWN: no logger accuracy statement is published",
                "provenance": "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip, archive sha256 82302a7d…, "
                              "owner-approved download (2026-10-14)",
                "prior_forge_use": note, "classes": sorted(classes), "outcome_known_in_evaluator_context":
                    "HISTORICAL_TRUTH_EXPOSED" in classes, "structural_screen_failures": reasons, "primary_class": primary})
    return rows


def lg_rows() -> list[dict[str, Any]]:
    raw = DATA / "lg_hg2" / "raw"
    out = []
    for name, classes, note in (
            ("549_HPPC.csv", {"USED_IN_V0", "USED_IN_V1", "USED_IN_V2", "HISTORICAL_TRUTH_EXPOSED"},
             "v0/v1 P2 and v2 Q2 pulse windows; identifiability study result (IDENTIFIABLE, 2C/4C pulses 12.6 mV) known"),
            ("551_Cap_1C.csv", {"USED_IN_V0", "USED_IN_V1", "HISTORICAL_TRUTH_EXPOSED"},
             "v0/v1 held-out constant-current test; FAILS at 28.7 mV in the identifiability study (known)"),
            ("549_C20DisCh.csv", {"UNUSED_BY_MIND"}, "not in a Mind pack; same cell and session as the exposed HPPC/1C "
                                                     "results, whose constant-current failure predicts its direction"),
            ("549_Dis_0p5C.csv", {"UNUSED_BY_MIND"}, "as above"),
            ("549_Dis_2C.csv", {"UNUSED_BY_MIND"}, "as above")):
        p = raw / name
        primary = "ELIGIBLE_SECONDARY_ONLY"
        if "UNUSED_BY_MIND" in classes:
            classes = classes | {"HISTORICAL_TRUTH_EXPOSED"}
        out.append({"dataset": "LG 18650HG2 (McMaster, Mendeley cp3473x7xv.3), 25 C", "unit": "one cell", "condition": name,
                    "identity": {"file": f"lg_hg2/raw/{name}", "sha256": _sha(p)},
                    "temperature": {"ambient_label_C": 25}, "protocol": {"file": name},
                    "channels": ["Time", "Voltage", "Current", "Temperature", "Capacity"],
                    "uncertainty": "DECLARED_TYPE_B: publisher accuracy 0.1 % of 5 V full scale (independence not declared)",
                    "provenance": "Mendeley-published sha256 per file (MENDELEY_MANIFEST.json)", "prior_forge_use": note,
                    "classes": sorted(classes), "outcome_known_in_evaluator_context": True,
                    "structural_screen_failures": [], "primary_class": primary})
    out.append({"dataset": "LG 18650HG2, other temperatures (-20..40 C)", "unit": "416 files", "condition": "not downloaded",
                "identity": {"manifest": "lg_hg2/MENDELEY_MANIFEST.json"}, "temperature": None, "protocol": None,
                "channels": None, "uncertainty": "as above", "provenance": "published, not local",
                "prior_forge_use": "none", "classes": ["UNUSED_BY_MIND"], "outcome_known_in_evaluator_context": False,
                "structural_screen_failures": ["not available locally: a download needs the owner's approval"],
                "primary_class": "INELIGIBLE"})
    return out


KIRKALDY_META = {  # experiment_metadata.xlsx (Zenodo 10637534): expt -> cell -> (ageing temperature C, rig, channel)
    4: {"A": (10, 2, "CC1"), "B": (10, 2, "CC2"), "C": (10, 2, "CC3"), "D": (25, 5, "CE1"), "E": (25, 5, "CE2"),
        "F": (40, 5, "CE3"), "G": (40, 5, "CE4"), "H": (40, 5, "CE5")},
    5: {"A": (10, 2, "CC4"), "B": (10, 2, "CC5"), "C": (10, 2, "CC6"), "D": (25, 2, "CC7"), "E": (25, 2, "CC8"),
        "F": (40, 5, "CE6"), "G": (40, 5, "CE7"), "H": (40, 5, "CE8")},
}


def kirkaldy_rows() -> list[dict[str, Any]]:
    extract = json.loads((VAULT / "EXTRACT_MANIFEST.json").read_bytes())
    out = []
    for expt, cells in KIRKALDY_META.items():
        for cell, (age_T, rig, channel) in cells.items():
            used = cell in ("D", "E")
            members = {k: v for k, v in extract["members"].items() if v["expt"] == expt and v["cell"] == cell}
            classes = {"UNUSED_BY_MIND"} | ({"HISTORICAL_TRUTH_EXPOSED"} if used else set())
            temps = {}
            for name in members:
                a = np.loadtxt(DATA / "kirkaldy2024" / "v3_rpt" / name, delimiter=",", skiprows=1, usecols=(4,))
                temps[name] = [float(a.min()), float(a.max())]
            out.append({
                "dataset": "Kirkaldy et al. 2024 LG M50T 21700 degradation (Zenodo 10637534, CC-BY-4.0)",
                "unit": f"Expt {expt} cell {cell}", "condition": "RPT GITT (25-pulse, 0.5C) at RPT0 and the latest common RPT"
                if not used else "BoL RPT (used by the cross-cell 1RC study)",
                "identity": {"archive": extract["archives"][str(expt)]["file"],
                             "archive_md5": extract["archives"][str(expt)].get("md5"),
                             "members": {k: v["sha256"] for k, v in members.items()}},
                "temperature": {"ageing_C": age_T, "rpt_recorded_cell_C_range": temps},
                "protocol": {"rig": rig, "channel": channel, "gitt": "CC-CV top-up, ~2 h rest, 25 x 288 s pulses at 2.5 A "
                             "(0.1 s sampling) each followed by a 3660 s rest (1 s sampling), last pulse ends at the cutoff, "
                             "6 h final rest"},
                "channels": ["Time (s)", "Voltage (V)", "Current (mA)", "Charge (mA.h)", "Temperature (degC)"],
                "uncertainty": "UNKNOWN: the record does not state the BioLogic cycler's accuracy (the cross-cell 1RC "
                               "preregistration also declared UNKNOWN)",
                "provenance": "Zenodo md5 per archive (verified by extract.py --verify-archives), sha256 per extracted member",
                "prior_forge_use": ("battery_1rc_crosscell calibration cell (RPT0 GITT/0.1C; IDENTIFIABILITY_SUPPORTED known)"
                                    if used else "BIG14 fade study used this cell's per-cycle summary capacity only (an "
                                                 "ageing-law question, outcome NOT MET known); no voltage/1RC use"),
                "classes": sorted(classes), "outcome_known_in_evaluator_context": used,
                "structural_screen_failures": [],
                "primary_class": "ELIGIBLE_SECONDARY_ONLY" if used else "ELIGIBLE_PRIMARY_V3"})
    for expt, cells in ((1, "DEF"), ("2,2", "CD"), (3, "DEF")):
        for cell in cells:
            out.append({"dataset": "Kirkaldy et al. 2024 LG M50T", "unit": f"Expt {expt} cell {cell}",
                        "condition": "BoL RPT (D:/forge-data/kirkaldy2024/bol25)",
                        "identity": {"manifest": "kirkaldy2024/bol25.sha256"}, "temperature": None, "protocol": None,
                        "channels": None, "uncertainty": "UNKNOWN", "provenance": "bol25.sha256",
                        "prior_forge_use": "battery_1rc_crosscell (calibration or held-out); held-out cells no longer blind",
                        "classes": ["HISTORICAL_TRUTH_EXPOSED", "UNUSED_BY_MIND"], "outcome_known_in_evaluator_context": True,
                        "structural_screen_failures": [], "primary_class": "ELIGIBLE_SECONDARY_ONLY"})
    out.append({"dataset": "Kirkaldy et al. 2024, Expt 1, 2,2, 3 other cells and later RPTs",
                "unit": "archives not local", "condition": "-", "identity": {"zenodo": "10637534"}, "temperature": None,
                "protocol": None, "channels": None, "uncertainty": "UNKNOWN", "provenance": "published, not local",
                "prior_forge_use": "none", "classes": ["UNUSED_BY_MIND"], "outcome_known_in_evaluator_context": False,
                "structural_screen_failures": ["not available locally: a download needs the owner's approval"],
                "primary_class": "INELIGIBLE"})
    return out


def chen_rows() -> list[dict[str, Any]]:
    manifest = json.loads((ROOT / "benchmarks" / "measurements" / "chen2020_lgm50" / "manifest.json").read_bytes())
    out = []
    for name, entry in manifest["files"].items():
        p = DATA / "chen2020_lgm50" / name
        sha = _sha(p)
        out.append({"dataset": "Chen et al. 2020 LG M50 validation discharges (Zenodo 4032561, CC-BY-4.0)",
                    "unit": name.replace(".csv", ""), "condition": "CC discharges at 0.5, 2.5, 5 and 7.5 A to 2.5 V after "
                    "CC-CV charge to 4.2 V (C/100 termination) and 2 h rest; 30 s sampling",
                    "identity": {"file": f"chen2020_lgm50/{name}", "sha256": sha, "pinned_sha256": entry["sha256"],
                                 "matches_pin": sha == entry["sha256"]},
                    "temperature": {"chamber_C": "~26.6-28", "cell": "26-58 C (self-heating at 7.5 A)"},
                    "protocol": {"tester": "Maccor #3", "rates_A": [0.5, 2.5, 5.0, 7.5], "termination_A": 0.05},
                    "channels": ["Test Time", "Current", "Voltage", "Capacity", "Temperature Cell", "Temperature Chamber"],
                    "uncertainty": "UNKNOWN: no tester accuracy is stated in the record",
                    "provenance": "Zenodo md5 equals the record (benchmarks/measurements/chen2020_lgm50/manifest.json)",
                    "prior_forge_use": "BIG 14 model-measurement validation (PyBaMM, non-Mind); no outcome is known in the "
                                       "evaluator context (not read)",
                    "classes": ["UNUSED_BY_MIND"], "outcome_known_in_evaluator_context": False,
                    "structural_screen_failures": [] if sha == entry["sha256"] else ["provenance: sha256 mismatch"],
                    "primary_class": "ELIGIBLE_PRIMARY_V3" if sha == entry["sha256"] else "INELIGIBLE"})
    return out


def bridge_rows() -> list[dict[str, Any]]:
    pack = ROOT / "benchmarks" / "battery_rediscovery_v2" / "candidate" / "pack"
    return [{"dataset": "battery_rediscovery_v2 pack", "unit": pid, "condition": "exact v2 candidate-visible problem",
             "identity": {"file": f"benchmarks/battery_rediscovery_v2/candidate/pack/{pid}.json", "sha256": _sha(pack / f"{pid}.json")},
             "temperature": None, "protocol": None, "channels": None, "uncertainty": "as declared in the pack",
             "provenance": "v2 SEAL.json", "prior_forge_use": "v2 (sealed, evaluated)",
             "classes": ["USED_IN_V2", "HISTORICAL_TRUTH_EXPOSED"], "outcome_known_in_evaluator_context": True,
             "structural_screen_failures": [], "primary_class": "ELIGIBLE_SECONDARY_ONLY",
             "use": "SECONDARY_BRIDGE_SET: re-run under the v3 harness to show the GEN1 outputs reproduce; never counted in "
                    "the primary conclusion"} for pid in ("Q1", "Q2")]


def build() -> dict[str, Any]:
    rows = nasa_rows() + lg_rows() + kirkaldy_rows() + chen_rows() + bridge_rows()
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["primary_class"]] = counts.get(r["primary_class"], 0) + 1
    return {"schema": "forge.battery_rediscovery_v3.census/1", "screen": SCREEN, "rows": rows, "counts": counts,
            "note": "written before any v3 truth exists; no fit and no model comparison was made to classify a unit"}


def main() -> int:
    c = build()
    write_json(VAULT / "CENSUS.json", c)
    print(json.dumps(c["counts"]))
    for r in c["rows"]:
        print(f"{r['primary_class']:24s} {r['unit']:18s} {r['condition'][:40]:40s} {'; '.join(r['structural_screen_failures'])[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
