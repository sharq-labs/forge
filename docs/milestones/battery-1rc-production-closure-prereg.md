# Battery 1RC Production Closure — Raw NASA Ingestion Preregistration

**Capability:** `battery.thevenin_1rc`  
**Stage before this round:** `FOUNDATION`  
**Scope of this round:** raw NASA PCoE Li-ion Battery Aging ingestion only.

## Hypothesis

Forge can ingest one NASA PCoE battery-aging MATLAB cell file into a deterministic,
auditable canonical record without inventing scientific information that is absent
from the source.

This round does **not** claim calibration, validation, uncertainty closure, or
production readiness. The `real_data` capability gate remains `MISSING` until the
importer is run against pinned raw NASA bytes and the resulting receipt/canonical
record is committed or otherwise frozen as evidence.

## Source contract

NASA documents a top-level `cycle` structure array with operation type
`charge`, `discharge`, or `impedance`, ambient temperature, a MATLAB date vector,
and operation-specific measurement channels. Charge/discharge cycles include
measured terminal voltage, output current, battery temperature and a sample-time
vector; discharge also includes delivered capacity.

The importer preserves those source-declared cycle boundaries. It does not infer
sub-cycle pulse/rest labels.

## Proof obligations

1. **Byte identity** — exact raw bytes are receipted with SHA-256 and byte count
   before parsing.
2. **Determinism** — the same parsed source content plus the same receipt yields
   the same canonical digest.
3. **No hidden sign convention** — `Current_measured` is preserved exactly as
   recorded. Ingestion performs no charge/discharge sign normalization.
4. **No invented state** — state of charge is not inferred.
5. **No invented experiment structure** — pulse/rest segmentation is not inferred.
6. **No invented uncertainty** — sensor uncertainty is recorded as `UNKNOWN`.
7. **No premature model identification** — R0/R1/C1/OCV parameters are not fitted
   or inferred in this round.
8. **Operational alignment** — voltage/current/temperature/time sample arrays for
   charge/discharge cycles must have equal, non-zero lengths and non-decreasing time.
9. **Discharge capacity** — a discharge cycle without positive finite `Capacity`
   is refused.
10. **Impedance preservation** — real/complex impedance channels are retained;
    complex values are represented explicitly by real/imaginary parts.
11. **Fail closed** — malformed structures, unknown cycle types and non-finite
    required data are refused instead of repaired or guessed.

## Fail conditions

This round fails if any of the following occurs:

- a raw file can be parsed without an exact byte receipt;
- two identical inputs produce different canonical digests;
- malformed operational channels are accepted;
- SOC, pulse/rest labels, sensor uncertainty, or 1RC parameters appear as inferred
  scientific facts;
- an unknown operation type is silently mapped to a supported type;
- impedance data are discarded merely because they are not used by the 1RC kernel.

## Deferred to later rounds

- raw NASA archive acquisition and frozen source receipt;
- cell-level calibration/validation split;
- identifiability analysis for OCV/R0/R1/C1;
- Rint vs 1RC held-out metrics;
- measurement uncertainty;
- parameter uncertainty;
- model-form discrepancy;
- production model/realization registration;
- claims and DomainPack integration;
- promotion beyond `FOUNDATION`.
