# NASA battery ALT measurement pack

This directory records the source contract for the **Randomized and
Recommissioned Battery Dataset** published through NASA's Prognostics Center of
Excellence.

Source:
- NASA Open Data landing page: https://data.nasa.gov/dataset/randomized-and-recommissioned-battery-dataset
- NASA NTRS data description: https://ntrs.nasa.gov/citations/20230014884
- Public archive endpoint recorded by the catalog: https://data.nasa.gov/docs/legacy/battery_alt_dataset.zip

The source describes continuous pack-level CSV logging with columns for time,
mode, charger/load voltage, battery/load-board temperatures, load current and
mission type. The dataset contains independent battery packs under constant and
variable loading conditions.

## Forge admission rule

The manifest is **source metadata, not a trust pin**. The raw archive is not
vendored here, and the catalog metadata hash is not represented as the archive
byte hash.

The reviewed NASA metadata/data description does not state a calibrated
per-observation sensor uncertainty. Therefore a row imported from this dataset
starts with `Uncertainty.UNKNOWN` and cannot become an admissible
`MeasurementRecord` until all of the following are supplied and bound:

1. complete operating context required by the target Forge capability;
2. a quantified measurement uncertainty attributed to `MEASUREMENT`;
3. a calibration reference;
4. provenance for the extracted row/data product.

For model-form discrepancy work, calibration and validation are split by
**whole battery pack**, not by randomly mixing rows from the same pack. This
prevents correlated observations from appearing on both sides of a held-out
test.

## What this pack does not claim

- NASA publication does not validate Forge's battery model.
- A public dataset is not automatically trusted evidence.
- Agreement with these measurements does not establish zero model-form error.
- The current discrepancy producer emits a non-authoritative candidate only;
  it does not satisfy a MODEL_FORM uncertainty requirement.
