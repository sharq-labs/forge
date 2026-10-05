# NASA Li-ion Battery Aging measurement pack

This pack describes the NASA Ames Prognostics Center of Excellence Li-ion
Battery Aging Dataset used to exercise Forge's battery measurement boundary.

Official source metadata describes commercially available **18650 cells**
cycled through charge, discharge and EIS profiles at different temperatures.
Recorded discharge channels include terminal voltage, battery output current,
battery temperature, time and delivered capacity. NASA describes a voltmeter,
ammeter and thermocouple sensor suite and an acquisition rate of about 10 Hz.

Sources:
- https://data.nasa.gov/dataset/li-ion-battery-aging-datasets
- https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/
- archive listed by the NASA repository:
  https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip

## Forge interpretation

Direct channels:
- `Voltage_measured` -> terminal voltage observation
- `Current_measured` -> operating current after an explicitly declared sign convention
- `Temperature_measured` -> measured cell temperature
- `ambient_temperature` -> environmental operating condition

Not direct measurements:
- state of charge
- R0 / R1 / C1
- model-form discrepancy
- sensor uncertainty

SOC may be reconstructed from measured current only when an initial SOC and a
reference capacity are declared. Forge labels that result **derived** and does
not let it masquerade as measurement evidence.

The NASA catalog/data description reviewed for this pack does not state a
calibrated per-sample uncertainty for the voltage/current/temperature channels.
Therefore imported observations start with UNKNOWN measurement uncertainty and
cannot become admissible production measurement evidence merely because NASA is
the publisher.

## Battery Physics v2 relationship

The new `engcore.domains.battery.thevenin` kernel represents one dynamic
polarization branch:

```
tau = R1 C1
Vp(t+dt) = Vp(t) exp(-dt/tau) + I R1 (1 - exp(-dt/tau))
Vt = OCV(z) - I R0 - Vp
```

It supports zero-current relaxation, which is essential for pulse/rest
characterization. It is intentionally **not** registered as the production
battery capability yet. Parameter identification, independent held-out
validation and measurement uncertainty must be established first.


## Deterministic raw-file ingestion

`tools.nasa_battery_aging` is the first production-closure step for the 1RC line.
It receipts the exact `.mat` bytes with SHA-256, parses NASA's documented
`cycle` structure with `scipy.io.loadmat(..., simplify_cells=True)`, preserves
charge/discharge/impedance cycles in source order, validates aligned operational
sample arrays, and emits deterministic canonical JSON.

Example:

```bash
python -m tools.nasa_battery_aging /path/to/B0005.mat \
  --out /path/to/B0005.canonical.json
```

The importer deliberately does **not** infer SOC, pulse/rest segments, sensor
uncertainty, or R0/R1/C1 parameters. `Current_measured` is preserved exactly as
recorded; no sign normalization occurs at ingestion. A future calibration round
may derive additional quantities only under a separately preregistered evidence
contract.

Adding the importer does not close the capability matrix's `real_data` gate.
That gate remains missing until raw NASA bytes are actually acquired, receipted,
ingested, and frozen as evidence.

The receipt and parser consume the same in-memory byte snapshot, so replacing
an input path during parsing cannot attach a different file's digest. Physical
operational channels must be finite real numeric vectors; MATLAB row/column
vectors and squeezed singleton samples are accepted, while matrices, strings,
logical values and complex operational measurements are refused. Impedance
channels retain finite complex values; empty impedance records are refused.

Dataset identifiers and URLs describe the intended source format. They do not
authenticate an arbitrary local file as NASA data. The lower-level
`canonicalize_loaded_mat` helper accepts a caller-supplied receipt for parsed
content; it cannot verify that receipt against raw bytes. Only `ingest_mat_file`
binds the receipt to the parsed byte snapshot. Neither API admits scientific
evidence or assigns calibration/validation roles. Cell-level split and leakage
controls remain a later preregistered obligation.
