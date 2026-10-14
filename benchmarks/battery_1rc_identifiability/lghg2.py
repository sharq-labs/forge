"""Read the LG HG2 (McMaster, doi:10.17632/cp3473x7xv.3, CC BY 4.0) Digatron CSV exports exactly as published.

Bytes in, typed columns out. Declared byte-level rules: NUL bytes (the exports carry one) and CRLF line endings are
tolerated; rows must arrive in non-decreasing Prog Time, and a row that goes back in time refuses the file. Rows that
share a Prog Time are one logged sample written twice (the logger re-reads the last sample of a step): the first is
kept when the repeats agree within the published instrument accuracy (0.1 % of full scale: 5 mV, 75 mA; step, status
and temperature exactly; the Ah counter, which no analysis reads, may advance by one sample and is only recorded), and the file is refused otherwise. The count and the largest disagreement are recorded. Current is preserved as recorded (Digatron: negative = discharge). Nothing is fitted or labelled here.
"""

from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass

import numpy as np


class LgHg2FileRefused(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    name: str
    sha256: str
    byte_count: int
    header: dict
    step: np.ndarray
    status: tuple
    prog_time_s: np.ndarray
    voltage_v: np.ndarray
    current_a: np.ndarray
    temperature_c: np.ndarray
    capacity_ah: np.ndarray
    dropped_exact_duplicates: int
    repeated_stamps: int
    max_repeat_disagreement: tuple


VOLTAGE_ACCURACY_V = 0.005      # 0.1 % of the 5 V channel (dataset readme)
CURRENT_ACCURACY_A = 0.075      # 0.1 % of the 75 A channel (dataset readme)


def _hms(text: str) -> float:
    h, m, s = text.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def read(path: pathlib.Path) -> Record:
    raw = pathlib.Path(path).read_bytes()
    text = raw.replace(b"\x00", b"").decode("latin-1").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("Time Stamp,Step,Status,Prog Time"))
    except StopIteration:
        raise LgHg2FileRefused(f"{path.name}: no Digatron column header") from None
    header = {}
    for line in lines[:start]:
        if "," in line:
            k, _, v = line.partition(",")
            header[k.strip()] = v.strip().rstrip(",")
    cols = lines[start].split(",")
    want = {name: cols.index(name) for name in ("Step", "Status", "Prog Time", "Voltage", "Current", "Temperature",
                                                 "Capacity")}
    rows, times, dup, repeats, worst_v, worst_i, worst_counter = [], {}, 0, 0, 0.0, 0.0, 0.0
    for line in lines[start + 2:]:
        if not line.strip():
            continue
        f = line.split(",")
        t = _hms(f[want["Prog Time"]])
        values = (int(f[want["Step"]]), f[want["Status"]], t, float(f[want["Voltage"]]), float(f[want["Current"]]),
                  float(f[want["Temperature"]]), float(f[want["Capacity"]]))
        if t in times:
            first = times[t]
            if first == values:
                dup += 1
                continue
            dv, di = abs(first[3] - values[3]), abs(first[4] - values[4])
            worst_counter = max(worst_counter, abs(first[6] - values[6]))
            if (first[:3] != values[:3] or first[5] != values[5] or dv > VOLTAGE_ACCURACY_V
                    or di > CURRENT_ACCURACY_A):
                raise LgHg2FileRefused(f"{path.name}: Prog Time {t} repeats with values that disagree beyond the "
                                       f"instrument accuracy (dV={dv:.5f} V, dI={di:.5f} A)")
            repeats += 1
            worst_v, worst_i = max(worst_v, dv), max(worst_i, di)
            continue
        if rows and t < rows[-1][2]:
            raise LgHg2FileRefused(f"{path.name}: Prog Time {t} goes back in time; rows are refused, never reordered")
        times[t] = values
        rows.append(values)
    arr = list(zip(*rows))
    out = Record(path.name, hashlib.sha256(raw).hexdigest(), len(raw), header, np.array(arr[0]), tuple(arr[1]),
                 np.array(arr[2]), np.array(arr[3]), np.array(arr[4]), np.array(arr[5]), np.array(arr[6]), dup, repeats,
                 (worst_v, worst_i, worst_counter))
    if not all(np.isfinite(x).all() for x in (out.prog_time_s, out.voltage_v, out.current_a, out.temperature_c)):
        raise LgHg2FileRefused(f"{path.name}: non-finite measurement")
    return out
