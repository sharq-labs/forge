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
