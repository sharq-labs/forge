"""Measured battery data: canonical ingestion, receipts, splits and the 1RC identifiability gate.

This package is the canonical owner of battery real-data ingestion in the
domain layer. The older paths stay where they are as compatibility code and
are not scientific authority:

* ``engcore.claims.adapters.nasa_battery_aging`` maps one NASA sample to a
  claims-layer ``DatasetObservation``; it parses nothing from bytes;
* ``benchmarks/reference_validation/battery_nasa.py`` is benchmark tooling
  that normalizes NASA ``.mat`` files into reference points.

Modules
-------
- ``ingest``           source formats, byte pins, normalization, lineage, receipts, derived channels
- ``sources``          the declared raw sources this package can read (Jahn 2024 A123 HysPowerTest)
- ``quality``          deterministic segmentation and the data-quality report (classifies, never cleans)
- ``split``            calibration / holdout over whole groups, bound to a receipt, with the leakage guard
- ``identifiability``  the structural and practical identifiability gate for ``battery.thevenin_1rc``

Nothing here calibrates a model, validates one, or produces evidence. The
gate's output is CAN_CALIBRATE or a refusal / review with its reasons.
"""

from .identifiability import (
    DEFAULT_DESIGN,
    GateDecision,
    IdentifiabilityDesign,
    IdentifiabilityGateReport,
    VoltageNoiseDeclaration,
    assess_thevenin_1rc_identifiability,
    thevenin_1rc_overpotential,
)
from .ingest import (
    BatteryDataset,
    BatteryDatasetReceipt,
    BatteryTimeSeries,
    Channel,
    ColumnDeclaration,
    CurrentSign,
    DerivedChannel,
    LineageKind,
    RawFileDeclaration,
    RealDataError,
    SourceFormat,
    derive_state_of_charge,
    ingest_dataset,
    ingest_raw_file,
)
from .quality import DEFAULT_SEGMENTATION, SegmentationPolicy, quality_report, segment_series
from .split import CalibrationHoldoutSplit, SplitPolicy, SplitUnit, build_split, calibration_series

__all__ = [
    "BatteryDataset",
    "BatteryDatasetReceipt",
    "BatteryTimeSeries",
    "CalibrationHoldoutSplit",
    "Channel",
    "ColumnDeclaration",
    "CurrentSign",
    "DEFAULT_DESIGN",
    "DEFAULT_SEGMENTATION",
    "DerivedChannel",
    "GateDecision",
    "IdentifiabilityDesign",
    "IdentifiabilityGateReport",
    "LineageKind",
    "RawFileDeclaration",
    "RealDataError",
    "SegmentationPolicy",
    "SourceFormat",
    "SplitPolicy",
    "SplitUnit",
    "VoltageNoiseDeclaration",
    "assess_thevenin_1rc_identifiability",
    "build_split",
    "calibration_series",
    "derive_state_of_charge",
    "ingest_dataset",
    "ingest_raw_file",
    "quality_report",
    "segment_series",
    "thevenin_1rc_overpotential",
]
