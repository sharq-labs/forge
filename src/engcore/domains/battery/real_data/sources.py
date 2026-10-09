"""Declared raw sources the canonical battery ingestion knows how to read.

Each entry is a statement made BEFORE the bytes are read: who published the
data, under which licence, the exact byte pin of every file, what every column
means and on what basis. Nothing here is inferred from the data; where the
source is silent (the Jahn 2024 CSVs carry no unit row) the declaration says
so, and ingestion verifies the declaration against the data instead of
trusting it.

Jahn 2024, A123 18650M1A hysteresis power tests
-----------------------------------------------
Zenodo record 10.5281/zenodo.11958572 (CC BY 4.0), the data of
doi:10.1038/s44172-024-00221-4. One cell (file label ``A123_01``), BaSyTec
CTS tester, Binder climate chamber at 25 degC. The two HysPowerTest files are
two separate test sequences on that one cell. Each is an ``n x 4`` record
``[t Q I U]``; the record description states no units. Forge declares
second / ampere-hour / ampere / volt, and positive current as charge.
Ingestion refuses the file unless the tester's own ampere-hour counter
matches the trapezoidal integral of the current (which checks the time unit
and the ratio of the current and charge units -- not a common scale error --
and ties the counter's sign to the current's), and unless the voltage moves
against the discharge current at every clear current step (which fixes which
sign is discharge). The files carry no temperature channel: the 25 degC
chamber setpoint is source metadata, never a per-sample measurement.

The byte pins are the ones recorded at acquisition in
``benchmarks/battery_flagship_b3/evidence/PROVENANCE.json``; a test holds the
two in agreement.
"""

from __future__ import annotations

from ....scientific.corpus import ReferenceSource, SourceSnapshot
from .ingest import (
    Channel,
    ColumnDeclaration,
    CurrentSign,
    LineageKind,
    RawFileDeclaration,
    SourceFormat,
)

JAHN_2024_SOURCE = ReferenceSource(
    source_id="zenodo.jahn2024.pdecm_data",
    authority="Jahn, L. (University of Bayreuth): Probability distributed equivalent circuit model - Data",
    domain="battery",
    source_version="10.5281/zenodo.11958572",
    landing_url="https://zenodo.org/records/11958572",
    allowed_hosts=("zenodo.org",),
    license_note=(
        "CC BY 4.0. Cite 10.5281/zenodo.10852930 and doi:10.1038/s44172-024-00221-4. "
        "The four files of 10.5281/zenodo.11958572 used in this repository have the MD5 published for "
        "10.5281/zenodo.10852930."
    ),
    scale_note="One A123 18650M1A cell at a 25 degC chamber setpoint; two HysPowerTest sequences.",
)

_UNIT_BASIS = (
    "the Zenodo record describes the file as 'nx4 vector [t Q I U]' and states no units; Forge declares "
    "{unit}; ingestion checks the time unit and the ratio of the current and charge units against the "
    "tester's own ampere-hour counter (a common scale error in both would pass that check)"
)
_VOLTAGE_BASIS = (
    "the Zenodo record describes the file as 'nx4 vector [t Q I U]' and states no units; Forge declares volt, "
    "and ingestion refuses any value outside the declared single-cell window"
)
_SIGN_BASIS = (
    "declared positive-is-charge: the record's first phase raises the cell voltage to the 3.6 V constant-voltage "
    "limit while the current reads about +1.1 A; ingestion verifies the sign by the cell's passive step "
    "response (the voltage must move against the discharge current at every clear current step)"
)


def _hyspowertest_format(prefix: str, label: str) -> SourceFormat:
    t, q, i, u = (f"{name}_{prefix}_power" for name in ("t", "Q", "I", "U"))
    return SourceFormat(
        format_id=f"jahn2024.hyspowertest.{prefix}_power",
        format_version=1,
        description=(
            f"Jahn 2024 HysPowerTest CSV, {label} variant: header '{t},{q},{i},{u}', comma separated, one "
            "sample per record in measurement order, elapsed time from the start of the sequence"
        ),
        header=(t, q, i, u),
        columns=(
            ColumnDeclaration(t, Channel.TIME, "second", LineageKind.MEASURED, _UNIT_BASIS.format(unit="second")),
            ColumnDeclaration(
                q,
                Channel.CHARGE_COUNTER,
                "ampere_hour",
                LineageKind.SOURCE_COMPUTED,
                _UNIT_BASIS.format(unit="ampere_hour") + "; the counter is computed by the tester, not measured",
            ),
            ColumnDeclaration(i, Channel.CURRENT, "ampere", LineageKind.MEASURED, _UNIT_BASIS.format(unit="ampere")),
            ColumnDeclaration(u, Channel.VOLTAGE, "volt", LineageKind.MEASURED, _VOLTAGE_BASIS),
        ),
        current_sign=CurrentSign.POSITIVE_IS_CHARGE,
        current_sign_basis=_SIGN_BASIS,
        # A123 18650M1A: the record's own CC-CV limit is 3.6 V and its discharge cutoff 2.0 V. The window is
        # wider than both, so it refuses a wrong unit (millivolt, kilovolt) without judging the cell.
        voltage_window_v=(1.0, 5.0),
        charge_counter_tolerance_fraction=0.01,
        # Rest-current scatter in these files is about 1 mA and the voltage quantization 0.19 mV.
        sign_test_current_step_a=0.1,
        sign_test_voltage_step_v=1.0e-3,
    )


#: ``t_dc_power`` columns: the sequence that starts at 100 % SOC.
HYSPOWERTEST_DC_FORMAT = _hyspowertest_format("dc", "discharge-start")
#: ``t_ch_power`` columns: the sequence that starts at 0 % SOC.
HYSPOWERTEST_CH_FORMAT = _hyspowertest_format("ch", "charge-start")

CELL_ID = "A123_01"
_ACQUIRED = "2026-09-13"


def _snapshot(filename: str, sha256: str, byte_length: int) -> SourceSnapshot:
    return SourceSnapshot(
        source_id=JAHN_2024_SOURCE.source_id,
        source_version=JAHN_2024_SOURCE.source_version,
        snapshot_sha256=sha256,
        snapshot_url=f"https://zenodo.org/records/11958572/files/{filename}?download=1",
        byte_length=byte_length,
        retrieved_at_utc=_ACQUIRED,
        content_type="text/csv",
    )


SOC100_FILENAME = "20230125_HysPowerTest_A123_01_25deg_SOC100.csv"
SOC50_FILENAME = "20230125_HysPowerTest_A123_01_25deg_SOC50.csv"

HYSPOWERTEST_SOC100 = RawFileDeclaration(
    group_id="A123_01/HysPowerTest_SOC100",
    cell_id=CELL_ID,
    test_sequence_id="20230125_HysPowerTest_A123_01_25deg_SOC100",
    published_filename=SOC100_FILENAME,
    snapshot=_snapshot(
        SOC100_FILENAME, "009c2fb085e219c7b20afaa050ac9e69d848cf04fc6e9165ce2bbd1282357feb", 47380
    ),
    source_format=HYSPOWERTEST_DC_FORMAT,
)

HYSPOWERTEST_SOC50 = RawFileDeclaration(
    group_id="A123_01/HysPowerTest_SOC50",
    cell_id=CELL_ID,
    test_sequence_id="20230125_HysPowerTest_A123_01_25deg_SOC50",
    published_filename=SOC50_FILENAME,
    snapshot=_snapshot(
        SOC50_FILENAME, "d6e8b4b7ea4f832a67a859604ab8d507d2a1fdd7541cb37a485ac933dec92fd3", 20988
    ),
    source_format=HYSPOWERTEST_CH_FORMAT,
)

JAHN_2024_HYSPOWERTEST_FILES = (HYSPOWERTEST_SOC100, HYSPOWERTEST_SOC50)

#: Stated once and carried into the receipt's identity.
JAHN_2024_HYSPOWERTEST_ASSUMPTIONS = (
    "Units are not stated by the source; second, ampere_hour, ampere and volt are declared and verified "
    "against the tester's ampere-hour counter and the declared voltage window.",
    "Positive source current is charge; verified by the passive step response (the voltage moves against "
    "the discharge current at every clear step). The canonical current is the negation (positive is "
    "discharge).",
    "The recorded sample order is the measurement order. No row is reordered, deduplicated, smoothed or "
    "dropped; an unparseable row refuses the file.",
    "Rest-current scatter of about 1 mA is kept as recorded; segmentation classifies it, it is never zeroed.",
    "There is no temperature channel. The 25 degC chamber setpoint is source metadata and is not attached "
    "to any sample.",
    "State of charge is not a source channel and is not stored. The tester's ampere-hour counter is "
    "SOURCE_COMPUTED, not a measurement.",
    "Both files come from ONE physical cell (A123_01): they are two test sequences, not two cells.",
)

JAHN_2024_DATASET_ID = "jahn2024.a123_01.hyspowertest"

__all__ = [
    "CELL_ID",
    "HYSPOWERTEST_CH_FORMAT",
    "HYSPOWERTEST_DC_FORMAT",
    "HYSPOWERTEST_SOC100",
    "HYSPOWERTEST_SOC50",
    "JAHN_2024_DATASET_ID",
    "JAHN_2024_HYSPOWERTEST_ASSUMPTIONS",
    "JAHN_2024_HYSPOWERTEST_FILES",
    "JAHN_2024_SOURCE",
    "SOC100_FILENAME",
    "SOC50_FILENAME",
]
