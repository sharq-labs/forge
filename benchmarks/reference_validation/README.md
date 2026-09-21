# Forge Reference Validation — First Four Tracks

This package builds the ingestion and scoring boundary for four data-rich validation tracks:

1. **NIST SRD 69 thermophysical properties**
2. **NASA Ames PCoE Li-ion battery aging**
3. **NAFEMS thermal benchmarks**
4. **NIST SRD 17 chemical kinetics**

The Scientific Core remains offline. A live URL is never scientific authority.

## Evidence path

```text
official source
    -> immutable byte snapshot + SHA-256 manifest
    -> source-specific normalization
    -> ReferenceDataset
    -> explicit acceptance-tolerance review
    -> bulk campaign score
    -> OracleEvidenceSet
    -> repository trust pin (separate reviewed change)
    -> BENCHMARK_VALIDATED / EXPERIMENTALLY_VALIDATED
```

The separation is deliberate:

- **source value** is what the authority reported;
- **source uncertainty** is uncertainty reported by that source;
- **acceptance tolerance** is the Forge validation policy.

If acceptance tolerance is absent, the campaign records `unscored`. It does not infer success from the existence of a reference value.

## Track 1 — NIST SRD 69

`nist_properties.parse_nist_srd69_table` accepts a frozen tab/comma-delimited NIST property table and converts every supported property at every operating point into a `ReferencePoint`. Temperature and pressure are retained as operating conditions. Mixed liquid/vapour tables should be split with `phase_filter`; categorical phase is not smuggled into a numeric operating-point contract.

The first parser recognizes density, specific volume, Cp, Cv, enthalpy, internal energy, entropy, viscosity, thermal conductivity, speed of sound, surface tension and Joule-Thomson coefficient. Unit overrides are explicit; missing units are refused.

## Track 2 — NASA battery aging

`battery_nasa.parse_nasa_battery_mat` reads a frozen NASA MAT file with SciPy. The first campaign deliberately targets records the existing Forge battery vertical can meaningfully address:

- discharge terminal-voltage time series;
- measured cell-temperature time series;
- discharge capacity;
- impedance `Re` and `Rct`.

Measured current is treated as an operating condition, not as an output to "validate". Charge-cycle records are not silently counted as passed.

## Track 3 — NAFEMS thermal

Forge already has a stronger artifact than a new parser: the executable, repository-pinned NAFEMS P18.T3 vertical in `engcore.domains.thermal_models.nafems_t3`.

`thermal_nafems.run_existing_nafems_t3` exposes that existing benchmark to the campaign layer and reports whether `BENCHMARK_VALIDATED` was actually attained. Do not duplicate the T3 target or replace its trusted oracle with a second copy.

Additional NAFEMS cases should be added as separate frozen evidence identities. Respect the publication/license terms for any source material.

## Track 4 — NIST SRD 17 chemical kinetics

The SRD 17 web interface is not treated as a runtime API. A reviewed acquisition/normalization step produces CSV with this explicit schema:

```text
record_id,reaction,order,A,n,Ea_J_per_mol,temperature_K,reported_k,rate_unit,data_type,uncertainty_fraction
```

`rate_unit` must already be normalized to a Forge/Pint-compatible unit spelling. The original NIST record identity and reaction are retained.

The broad SRD 17 source is **not** labelled experimental: records include mixed experimental, theoretical and evaluated data. One promoted dataset is restricted to one reaction, because reaction identity is categorical rather than a numeric operating condition. Experimental validation may be granted only to a reviewed experimental-only subset.

## Trust promotion

Adding a dataset here does not make it trusted. After:

1. source bytes are frozen;
2. normalization is reviewed;
3. units and operating-point bindings are reviewed;
4. tolerance policy is justified;
5. the resulting `OracleEvidenceSet` digest is stable;

a separate repository change may add that exact identity to the Scientific Core's trusted oracle declarations. Until then the comparison can run and be reported, but it must not award a validation level.

This is intentional: the party importing data must not be able to grant itself scientific authority in the same step.
