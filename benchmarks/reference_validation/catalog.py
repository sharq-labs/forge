"""Pinned catalogue entries for the first four external validation tracks."""

from __future__ import annotations

from engcore.scientific.oracles import OracleKind

from .contracts import ReferenceSourceSpec


NIST_SRD69 = ReferenceSourceSpec(
    source_id="nist.srd69.thermophysical_properties",
    domain="thermophysical_properties",
    authority="NIST Chemistry WebBook, SRD 69",
    source_version="online",
    landing_url="https://webbook.nist.gov/chemistry/fluid/",
    oracle_kind=OracleKind.BENCHMARK_DATASET,
    allowed_hosts=("webbook.nist.gov",),
    scale_note=(
        "High-accuracy thermophysical-property tables across 74 fluids; suitable "
        "for dense temperature/pressure validation sweeps."
    ),
    license_note="Review NIST data-use terms before redistribution of snapshots.",
)

NASA_BATTERY_AGING = ReferenceSourceSpec(
    source_id="nasa.ames.pcoe.li_ion_battery_aging",
    domain="battery",
    authority="NASA Ames Prognostics Center of Excellence",
    source_version="repository snapshot",
    landing_url="https://data.nasa.gov/dataset/li-ion-battery-aging-datasets",
    oracle_kind=OracleKind.EXPERIMENTAL_DATASET,
    allowed_hosts=(\n        "data.nasa.gov",\n        "www.nasa.gov",\n        "nasa.gov",\n        "c3.nasa.gov",\n        "phm-datasets.s3.amazonaws.com",\n    ),
    scale_note=(
        "Run-to-failure charge/discharge/impedance measurements at multiple "
        "temperatures and loads."
    ),
    license_note="Preserve NASA dataset attribution and source metadata.",
)

NAFEMS_THERMAL = ReferenceSourceSpec(
    source_id="nafems.thermal.benchmarks",
    domain="thermal",
    authority="NAFEMS",
    source_version="catalogue + case-specific publication revision",
    landing_url="https://www.nafems.org/publications/glossaryofbenchmarks/thermalanalysis/",
    oracle_kind=OracleKind.BENCHMARK_DATASET,
    allowed_hosts=("www.nafems.org", "nafems.org"),
    scale_note=(
        "Standard thermal-analysis benchmark families spanning steady and "
        "transient conduction and several boundary-condition classes."
    ),
    license_note=(
        "Some NAFEMS publications are licensed/copyrighted; store only source "
        "material the project is entitled to redistribute."
    ),
)

NIST_CHEMICAL_KINETICS = ReferenceSourceSpec(
    source_id="nist.srd17.chemical_kinetics",
    domain="chemical_kinetics",
    authority="NIST Chemical Kinetics Database, SRD 17",
    source_version="Data Version 2026 / Web Version 7.1",
    landing_url="https://kinetics.nist.gov/kinetics/",
    # SRD 17 includes experimental, theoretical and other evaluated records.
    # The broad source is therefore reference/benchmark authority.  A later
    # normalized subset may be promoted to EXPERIMENTAL_DATASET only after its
    # record-level data_type has been reviewed.
    oracle_kind=OracleKind.BENCHMARK_DATASET,
    allowed_hosts=("kinetics.nist.gov",),
    scale_note=(
        "Tens of thousands of gas-phase reaction records with Arrhenius "
        "parameters, ranges, provenance and record-level data type."
    ),
    license_note="Preserve NIST record provenance and bibliographic references.",
)

FIRST_FOUR_SOURCES = (
    NIST_SRD69,
    NASA_BATTERY_AGING,
    NAFEMS_THERMAL,
    NIST_CHEMICAL_KINETICS,
)


def source_by_id(source_id: str) -> ReferenceSourceSpec:
    matches = [item for item in FIRST_FOUR_SOURCES if item.source_id == source_id]
    if len(matches) != 1:
        raise KeyError(source_id)
    return matches[0]


__all__ = [
    "FIRST_FOUR_SOURCES",
    "NASA_BATTERY_AGING",
    "NAFEMS_THERMAL",
    "NIST_CHEMICAL_KINETICS",
    "NIST_SRD69",
    "source_by_id",
]
