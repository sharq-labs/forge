"""Scientific domains built on the universal Scientific Core contracts.

A domain owns its physics, its components and its solver adapters. It never
adds domain-specific fields to the universal IR: everything here is a
*consumer* of ``engcore.scientific``, never a modifier of it.
"""

from ..scientific.results.result import (
    UNASSESSED_DECLARATIONS_ATTRIBUTE as _UNASSESSED_ATTRIBUTE,
)

#: Positions this package states on behalf of modules that cannot state their
#: own, keyed by module name. The core walks a constructing module's package
#: chain looking for exactly this attribute; it never learns what is in it.
#:
#: There is one entry, and it exists because of a freeze rather than because a
#: domain would rather not answer. ``thermal.conduction1d.solver`` builds
#: results that declare a model, and its source file is SHA-256 pinned by the
#: frozen ``thermal_t1`` experiment: adding an argument to the constructor call
#: inside it would break the pin that makes "T1 was not edited afterwards" a
#: checkable claim. So the position is stated here, one package above the
#: freeze, in the domain layer's own words rather than in the core's.
#:
#: Both spellings, because this repository is importable as ``engcore`` and as
#: ``src.engcore``, and a result constructed through one must not be judged by
#: whether the reader happened to use the other.
#:
#: This is not a place to be excused from answering. A guard in
#: ``tests/test_core_guards.py`` reads the frozen experiment configs and
#: refuses any entry here whose module is not actually pinned by one, so the
#: exemption is read off the freeze rather than remembered, and it expires the
#: day the freeze does.
_THERMAL_T1_FREEZE = (
    "not assessed: this result is produced by a module whose source is "
    "SHA-256 pinned by the frozen thermal_t1 experiment, so it cannot be "
    "edited to state its own position. The linear-diffusion model's validity "
    "domain is assessable and IS assessed on the unfrozen routes through the "
    "same physics (engcore.domains.thermal_models.conduction1d_schemes and "
    "conduction1d_bulk); this route reports the gap rather than the verdict"
)

SCIENTIFIC_UNASSESSED_DECLARATIONS: dict[str, str] = {
    "engcore.domains.thermal.conduction1d.solver": _THERMAL_T1_FREEZE,
    "src.engcore.domains.thermal.conduction1d.solver": _THERMAL_T1_FREEZE,
}

# The core reads this by name. If the name it reads and the name defined here
# ever part company, the declaration above becomes invisible and every result
# from the frozen module starts failing construction -- so the disagreement is
# caught here, at import, rather than there.
assert _UNASSESSED_ATTRIBUTE == "SCIENTIFIC_UNASSESSED_DECLARATIONS", (
    f"the core looks for {_UNASSESSED_ATTRIBUTE!r}; this package defines "
    f"SCIENTIFIC_UNASSESSED_DECLARATIONS"
)
