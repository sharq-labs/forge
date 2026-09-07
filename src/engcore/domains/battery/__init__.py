"""Equivalent-circuit battery cell with state of charge and self-heating.

A single cell — or a series string treated as one lumped cell — described by
the simplest useful equivalent circuit:

    V_terminal = OCV(SoC) - I R_int          (discharge, I positive out)
    SoC(t)     = SoC_0 - I t / (eta Q_nom)
    Q_gen      = I^2 R_int

Four scientific claims are declared, each as its own
:class:`~engcore.scientific.models.definition.ScientificModelDefinition` with
its own validity domain, so a caller may accept or reject them independently:

- ``models.RINT_OCV_MODEL``            terminal voltage and irreversible heat
- ``models.COULOMB_COUNTING_MODEL``    state of charge by charge integration
- ``models.CONSTANT_CURRENT_RUNTIME_MODEL``  time to a declared cutoff
- ``models.PEUKERT_DERATING_MODEL``    rate-dependent capacity derating

Modules
-------
- ``context``   the declaration records and the pure, unit-checked functions
                that derive every quantity a validity condition is stated over
- ``models``    the four model records, their thresholds and their realizations
- ``cell``      the cell and load declarations, the problem builders, and the
                ``assess_*`` entry points
- ``solver``    the closed-form evaluator for one discharge interval
- ``coupling``  a sequential self-heating run against the existing lumped
                thermal model

Nothing here is registered with, imported by, or known to
``engcore.scientific``. This package is a pure consumer of the core and of the
public API of ``engcore.domains.thermal_models``; it modifies neither.

What this domain deliberately does not model is stated in
``docs/domains/battery-v0.md`` and repeated in each model's ``assumptions``.
"""
