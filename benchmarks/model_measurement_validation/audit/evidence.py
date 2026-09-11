"""Reading the measured evidence off disk. No engcore, no model, no comparison.

This module does one thing: turn the files in ``evidence/`` into plain numbers,
exactly as their sources published them. It performs no fitting, no smoothing
and no interpolation, and it imports nothing from the Core.

The uncertainty budget is here too, because it is a property of the
measurement rather than of anything this round computes. It is assembled from
the instrument specifications the dataset's own Header sheet states, plus one
term measured from the data: how much each 24-hour relaxation was still moving
when it was stopped.
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import xml.etree.ElementTree as ET
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


# ---------------------------------------------------------------------------
# S-OCV: 24-hour relaxation traces
# ---------------------------------------------------------------------------


def _column_index(reference: str) -> int:
    letters = re.match(r"([A-Z]+)", reference).group(1)
    index = 0
    for character in letters:
        index = index * 26 + (ord(character) - 64)
    return index - 1


def _sheet_rows(archive, strings, sheets, name):
    sheet = ET.fromstring(archive.read("xl/" + sheets[name]))
    rows = []
    for row in sheet.iter(f"{NS}row"):
        cells = {}
        for cell in row.iter(f"{NS}c"):
            value = cell.find(f"{NS}v")
            if value is None:
                continue
            cells[_column_index(cell.get("r"))] = (
                strings[int(value.text)] if cell.get("t") == "s" else value.text
            )
        rows.append(cells)
    return rows


def _open_workbook(path):
    archive = zipfile.ZipFile(path)
    strings = [
        "".join(t.text or "" for t in si.iter(f"{NS}t"))
        for si in ET.fromstring(archive.read("xl/sharedStrings.xml")).iter(f"{NS}si")
    ]
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = {
        r.get("Id"): r.get("Target")
        for r in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    }
    sheets = {
        s.get("name"): relationships[s.get(f"{RS}id")]
        for s in workbook.iter(f"{NS}sheet")
    }
    return archive, strings, sheets


_SOC = re.compile(r"_(\d{2,3})-SOC$")


def relaxation_traces(sheet_name: str) -> dict:
    """Every OCV relaxation trace on one sheet, keyed by target state of charge.

    The relaxed value is the sample at t = 24 h, taken as published. The drift
    over the final hour is returned alongside it: the source does not state how
    complete the relaxation was, so this round measures it rather than assuming
    it is zero.
    """
    archive, strings, sheets = _open_workbook(EVIDENCE / "ocv_relaxation_24h.xlsx")
    rows = _sheet_rows(archive, strings, sheets, sheet_name)
    header = [rows[0].get(i) for i in range(len(rows[0]))]
    out = {}
    for column, label in enumerate(header):
        if column == 0 or not label:
            continue
        match = _SOC.search(label)
        if match is None:
            continue
        points = [
            (float(r[0]), float(r[column]))
            for r in rows[1:]
            if 0 in r and column in r
        ]
        at_23h = next(v for t, v in reversed(points) if t <= 23.0)
        out[int(match.group(1)) / 100.0] = {
            "label": label,
            "samples": len(points),
            "relaxed_voltage_v": points[-1][1],
            "voltage_at_23h_v": at_23h,
            "final_hour_drift_v": abs(points[-1][1] - at_23h),
            "initial_voltage_v": points[0][1],
        }
    return out


# ---------------------------------------------------------------------------
# The uncertainty budget for a relaxed OCV measurement
# ---------------------------------------------------------------------------
#
# Every term below is either an instrument specification quoted in the
# dataset's own Header sheet, or measured from the data. None is guessed, and
# none is set to zero because it was inconvenient.

#: NI USB-6251, 16-bit. The Header quotes 52 uV on the 0.1 V range down to
#: 1.920 uV on the 10 V range, plus a sensitivity of 28 uV. A 3.3 V cell is
#: read on the +/-5 V range; the sensitivity figure dominates and is used
#: whole rather than scaled, which is the conservative reading.
VOLTAGE_ACQUISITION_U_V = 28.0e-6

#: Allegro ACS724, +/-1.5% typical. Taken as a standard uncertainty on the
#: integrated charge, hence on the state of charge the cell was conditioned to.
SOC_RELATIVE_U = 0.015

#: The chamber holds 23 +/- 2 degC. LiFePO4's entropic coefficient dU/dT is a
#: fraction of a millivolt per kelvin over most of its range; 0.2 mV/K is a
#: deliberately generous figure for it, and 2 K is the full band rather than a
#: standard deviation, so this term is over- rather than under-stated.
TEMPERATURE_BAND_K = 2.0
ENTROPIC_COEFFICIENT_V_PER_K = 0.2e-3

COVERAGE_FACTOR = 2.0


def ocv_uncertainty(soc: float, traces: dict, drift_v: float) -> dict:
    """Combined standard uncertainty of one relaxed OCV, and its k=2 expansion.

    The state-of-charge term is the one that matters and the one that is easy
    to get wrong: an error in SOC is not an error in voltage until it is
    multiplied by how fast the voltage moves with SOC there. On a LiFePO4
    plateau that slope is small and the term nearly vanishes; at the ends it is
    an order of magnitude larger. The local slope is taken from the measured
    points on either side, so the budget follows the chemistry instead of
    assuming one number everywhere.
    """
    ordered = sorted(traces)
    index = ordered.index(soc)
    lower = ordered[max(0, index - 1)]
    upper = ordered[min(len(ordered) - 1, index + 1)]
    if upper == lower:
        slope = 0.0
    else:
        slope = abs(
            traces[upper]["relaxed_voltage_v"] - traces[lower]["relaxed_voltage_v"]
        ) / (upper - lower)
    soc_term = slope * SOC_RELATIVE_U * max(soc, 0.05)
    temperature_term = ENTROPIC_COEFFICIENT_V_PER_K * TEMPERATURE_BAND_K
    combined = math.sqrt(
        VOLTAGE_ACQUISITION_U_V**2
        + soc_term**2
        + temperature_term**2
        + drift_v**2
    )
    return {
        "state_of_charge": soc,
        "local_dOCV_dSOC_v": slope,
        "u_voltage_acquisition_v": VOLTAGE_ACQUISITION_U_V,
        "u_state_of_charge_v": soc_term,
        "u_temperature_v": temperature_term,
        "u_residual_relaxation_v": drift_v,
        "combined_standard_uncertainty_v": combined,
        "expanded_uncertainty_k2_v": COVERAGE_FACTOR * combined,
    }


# ---------------------------------------------------------------------------
# S-DCHG: decimated constant-current discharge curves
# ---------------------------------------------------------------------------


def discharge_curves() -> dict:
    return json.loads(
        (EVIDENCE / "discharge_curves_1min.json").read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# S-PT100: the standards-body resistance table
# ---------------------------------------------------------------------------

CELSIUS_MIN = -200
CELSIUS_MAX = 850


def platinum_table() -> dict:
    """The 1051-entry table, as ohms against degrees Celsius.

    The file stores ohms x 100 as unsigned 16-bit integers, which is exactly
    the 0.01 ohm resolution the transcription claims and is why the table can
    be parsed without loss.
    """
    text = (EVIDENCE / "pt100rtd_table.h").read_text(encoding="utf-8")
    # Cut at the FIRST closing brace after the initialiser opens. Splitting on
    # "};" instead runs past the array into the class declaration below it and
    # picks up eighteen stray digits from the method signatures, which is how
    # this parser first reported 1069 entries for a 1051-entry table.
    body = text.split("Pt100_table[1051] PROGMEM  = {", 1)[1].split("}", 1)[0]
    # Strip the trailing comment before extracting digits. The last line reads
    # "// Pt100 resistance * 100 at 850C", whose 100 and 850 a bare digit scan
    # happily adds to the table -- which is how this parser first reported
    # 1054 entries. Anything that changes the table length is refused below
    # rather than silently truncated.
    body = re.sub(r"//[^\n]*", "", body)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    values = [int(v) for v in re.findall(r"\d+", body)]
    if len(values) != 1051:
        raise ValueError(f"expected 1051 table entries, parsed {len(values)}")
    return {
        CELSIUS_MIN + index: value / 100.0 for index, value in enumerate(values)
    }
