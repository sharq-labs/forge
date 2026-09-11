"""Scientific domains built on the universal Scientific Core contracts.

A domain owns its physics, its components and its solver adapters. It never
adds domain-specific fields to the universal IR: everything here is a
*consumer* of ``engcore.scientific``, never a modifier of it.
"""

from types import MappingProxyType

from ..scientific.results.result import (
    UNASSESSED_DECLARATIONS_ATTRIBUTE as _UNASSESSED_ATTRIBUTE,
)
from ..scientific.results.thresholds import (
    THRESHOLD_DECLARATIONS_ATTRIBUTE as _THRESHOLD_ATTRIBUTE,
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
#: One spelling. The frozen experiments' ``src.engcore`` is an alias for these
#: same module objects (see ``src/__init__.py``), so a constructing module's
#: name is always its ``engcore`` name. This table used to carry both, because
#: the two spellings were two module trees and a result constructed through one
#: must not be judged by which the reader used; an entry under the alias could
#: no longer be read by anything.
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

#: The same statement, for the same freeze, about a different field.
#:
#: ``thermal.conduction1d.problem`` constructs the linear-diffusion model
#: record, and its source file is SHA-256 pinned by the frozen ``thermal_t1``
#: experiment -- so it cannot be edited to declare what that model excludes.
#: Its exclusions are real and are written in its own ``assumptions``: no
#: convection, no radiation, no phase change, no source term. A reader of a
#: credibility report still cannot see them, and that is the cost of the
#: freeze rather than a position this layer would rather not take.
#:
#: Closing it means editing a byte-pinned file and re-freezing three digest
#: tables, which would leave those digests attesting that the new bytes
#: produced the old recorded results. That is a worse record than an
#: undeclared exclusion list, and it is why this entry exists.
_THERMAL_T1_FREEZE_EXCLUSIONS = (
    "not declared: this model record is built by a module whose source is "
    "SHA-256 pinned by the frozen thermal_t1 experiment, so it cannot be "
    "edited to pass an exclusions argument. What it excludes is stated in its "
    "own assumptions -- one spatial dimension, no source term, no convection, "
    "no radiation, no phase change -- and is visible in the model record but "
    "not in a credibility report"
)

SCIENTIFIC_UNDECLARED_EXCLUSIONS: dict[str, str] = {
    "engcore.domains.thermal.conduction1d.problem": _THERMAL_T1_FREEZE_EXCLUSIONS,
}

SCIENTIFIC_UNASSESSED_DECLARATIONS: dict[str, str] = {
    "engcore.domains.thermal.conduction1d.solver": _THERMAL_T1_FREEZE,
}

# The core reads this by name. If the name it reads and the name defined here
# ever part company, the declaration above becomes invisible and every result
# from the frozen module starts failing construction -- so the disagreement is
# caught here, at import, rather than there.
assert _UNASSESSED_ATTRIBUTE == "SCIENTIFIC_UNASSESSED_DECLARATIONS", (
    f"the core looks for {_UNASSESSED_ATTRIBUTE!r}; this package defines "
    f"SCIENTIFIC_UNASSESSED_DECLARATIONS"
)

#: The threshold sets this layer's gates declare, pinned by gate.
#:
#: ``VerificationThresholds.is_declared`` is decided against this table and
#: nothing else. A gate's name is public, so a caller can build a set under it
#: with numbers of their own; the core awards a level only to a set whose gate
#: is registered here, whose version is the registered one, and whose values
#: hash to the registered digest. Any other set still runs every comparison and
#: awards nothing.
#:
#: Each digest is SHA-256 over the values exactly as
#: ``VerificationThresholds.threshold_digest`` serializes them. Changing a
#: declared number therefore means changing it in two places, on purpose: a
#: threshold that gates a level is a declaration, and a declaration that moves
#: should say so here. ``tests/test_trust_boundary_threshold_authority.py``
#: checks every entry against the constant it names, so a pin and its
#: declaration cannot drift apart silently.
#:
#: The conduction entry names a constant in a module byte-pinned by the frozen
#: thermal_t1 experiment. It is pinned from here, one package above the freeze,
#: for the reason the two tables above are.
SCIENTIFIC_THRESHOLD_DECLARATIONS = MappingProxyType({
    "electrical.dc.cross_solver": MappingProxyType({
        "declared_by": "engcore.domains.electrical.dc_consensus.DC_CONSENSUS_THRESHOLDS",
        "version": "0.1.0",
        "threshold_digest": "d2180283b327e990e93d8b5eeffa4d7e05c65f46c1040012dd463ac7409193ce",
    }),
    "electrical.dc.linear_residual": MappingProxyType({
        "declared_by": "engcore.domains.electrical.dc.validation.DC_CONVERGENCE_THRESHOLDS",
        "version": "0.1.0",
        "threshold_digest": "3f5290aba1f08882446beba6cb794512ee335c408a0e4cb6ed07d1ac0a41e9f5",
    }),
    "kinetics.cstr.verification_gate": MappingProxyType({
        "declared_by": "engcore.domains.kinetics.cstr.validation.CSTR_GATE_THRESHOLDS",
        "version": "0.1.0",
        "threshold_digest": "eec365d1bfa9271f2e590c13dd845fae7c2948e1ae67a624b2becd2c98c8c1e3",
    }),
    "thermal.conduction1d.refinement": MappingProxyType({
        "declared_by": "engcore.domains.thermal.conduction1d.validation.CONDUCTION_GATE_THRESHOLDS",
        "version": "0.1.0",
        "threshold_digest": "88b2ce9f040139bf34e827904917dbe0ea534445b81b74a525800a877f83291e",
    }),
})

assert _THRESHOLD_ATTRIBUTE == "SCIENTIFIC_THRESHOLD_DECLARATIONS", (
    f"the core looks for {_THRESHOLD_ATTRIBUTE!r}; this package defines "
    f"SCIENTIFIC_THRESHOLD_DECLARATIONS"
)
