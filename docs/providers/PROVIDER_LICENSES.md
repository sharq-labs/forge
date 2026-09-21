# Provider licence manifest

Diligence visibility, and nothing more. Every row states what the
distribution's own published metadata says, plus one fact about *this*
repository — how it uses the package. **No legal conclusion beyond that is
drawn or implied.**

The machine-readable version is `engcore.providers.licenses.PROVIDER_LICENSES`,
and `manifest_rows()` annotates each row with the version actually installed on
the host it is called from, so a drift between "the version this manifest was
written against" and "the version that ran" is visible rather than assumed away.
`tests/providers/test_provider_contract.py::test_the_license_manifest_covers_every_provider`
fails if a provider is added without a row.

| provider | version recorded | licence (per package metadata) | source repository |
|---|---|---|---|
| PyBaMM | 26.8.0.0 | BSD-3-Clause | https://github.com/pybamm-team/PyBaMM |
| PyBOP | 26.3 | BSD-3-Clause | https://github.com/pybop-team/PyBOP |
| SALib | 1.6.0 | MIT | https://github.com/SALib/SALib |

## Integration mode and distribution

All three: **optional runtime import**. None is vendored into this repository
and none is redistributed by it.

Each is declared as an optional extra in `pyproject.toml` —
`forge[battery-pybamm]`, `forge[battery-fit]`, `forge[sensitivity]` — and is
installed from PyPI by the operator. `src/engcore/providers/` imports each one
inside the function that needs it, never at module scope, so a Forge
installation that does not have them still imports, still runs, and reports
`PROVIDER_UNAVAILABLE` when asked for one.

The practical consequence, which is the question a reviewer actually has:
**shipping Forge does not ship PyBaMM, PyBOP or SALib.**

## Transitive dependencies

Not enumerated here. Installing `forge[battery-pybamm]` pulls PyBaMM's own
dependency tree (CasADi, xarray, sympy and others), each under its own licence,
and that tree is a property of the version resolved at install time rather than
of this repository. `EnvironmentIdentity.capture()` records the resolved
versions of the six that can change a number — pybamm, pybop, salib, casadi,
numpy, scipy — in the provenance of every run, which is where a reviewer
reconstructing a result should look.

Recorded 2026-09-21 from each distribution's PyPI metadata.
