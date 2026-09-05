"""Scientific simulation runtime.

Package layout:

- ``scientific``  universal core: problem IR, models, realizations, solvers,
                  results, provenance, validation, units
- ``domains``     scientific domains (electrical, thermal, kinetics) built on
                  the core without modifying it
- ``systems``     cross-domain compositions (electrothermal coupling,
                  multirotor study)
- ``sria``        evidence, admission, assurance, decision and campaign layer
- ``design``      design generation and design memory
- ``inference``   grid inference and admissibility
- ``uq``          predictive uncertainty and admission
- ``adequacy``    model adequacy against held-out observations
- ``data``        data boundary contracts
"""
